// SPDX-License-Identifier: MPL-2.0
// AMD temperature calculation adapted from LibreHardwareMonitor Amd17Cpu.cs.
// Copyright (C) LibreHardwareMonitor and Contributors; HaloStudio contributors.
// Reuse loaded drivers first; otherwise install the pinned official PawnIO once.
// Never install a second WinRing0 or stop/delete a shared driver/service.
// Its ONLY hardware write selects/restores the SMN read address at PCI 00:00.0/60.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <cpuid.h>
#include <bcrypt.h>
#include <wchar.h>

enum { OK=0, STARTING=1, UNSUPPORTED=2, NO_DRIVER=3, DENIED=4,
       BUSY=5, READ_FAILED=6, STOPPED=7, REBOOT=11, PREPARING=12, PACKAGE_ERROR=13 };
typedef struct {
    char magic[8]; uint32_t version, parent;
    uint64_t request, stamp;
    volatile LONG sequence; uint32_t status, raw, family, model;
    float temperature; uint32_t helper, stop;
    uint32_t backend, reused, samples, error;
} Snapshot;
_Static_assert(sizeof(Snapshot)==80, "IPC size");
typedef struct { uint32_t address, reg; } PciRead;
typedef struct { uint32_t address, reg, value; } PciWrite;
#define PCI_READ  ((40000u<<16)|(1u<<14)|(0x851u<<2))
#define PCI_WRITE ((40000u<<16)|(2u<<14)|(0x852u<<2))

static unsigned family, model; static char brand[49];
static unsigned backend, reused, sample_count, last_error;
static int cpu_supported(void) {
    unsigned a,b,c,d; char vendor[13]={0};
    __cpuid(0,a,b,c,d); memcpy(vendor,&b,4);memcpy(vendor+4,&d,4);memcpy(vendor+8,&c,4);
    __cpuid(1,a,b,c,d); unsigned base=(a>>8)&15;
    family=base==15?base+((a>>20)&255):base;
    model=(a>>4)&15; if(base==6||base==15)model|=((a>>16)&15)<<4;
    __cpuid(0x80000000,a,b,c,d);
    if(a>=0x80000004) for(unsigned i=0;i<3;i++) {
        __cpuid(0x80000002+i,a,b,c,d);unsigned words[]={a,b,c,d};memcpy(brand+16*i,words,16);
    }
    return !strcmp(vendor,"AuthenticAMD")&&(family==0x17||family==0x19||family==0x1A);
}
static float decode(uint32_t raw) {
    // CUR_TEMP [31:21], 0.125 C/LSB; RANGE_SEL or TJ_SEL can signal -49 C.
    float t=(raw>>21)*0.125f;
    if((raw&0x80000u)||((raw&0x30000u)==0x30000u))t-=49.0f;
    if(strstr(brand,"1600X")||strstr(brand,"1700X")||strstr(brand,"1800X"))t-=20.0f;
    else if(strstr(brand,"Threadripper 19")||strstr(brand,"Threadripper 29"))t-=27.0f;
    else if(strstr(brand,"2700X"))t-=10.0f;
    return t;
}
static int read_pci(HANDLE driver,uint32_t reg,uint32_t *value) {
    PciRead input={0,reg};DWORD got=0;
    return DeviceIoControl(driver,PCI_READ,&input,sizeof(input),value,4,&got,NULL)&&got==4;
}
static int select_smn(HANDLE driver,uint32_t value) {
    PciWrite input={0,0x60,value};DWORD got=0;
    return DeviceIoControl(driver,PCI_WRITE,&input,sizeof(input),NULL,0,&got,NULL);
}
static unsigned sample(HANDLE driver,HANDLE mutex,uint32_t *raw,float *temperature) {
    // Use the SAME global mutex as LHM/TrafficMonitor. Never sample unlocked.
    DWORD lock=WaitForSingleObject(mutex,10);
    if(lock!=WAIT_OBJECT_0&&lock!=WAIT_ABANDONED)return BUSY;
    uint32_t host=0,old=0;int selected=0;unsigned status=READ_FAILED;
    if(backend==2) {
        // Official signed AMDFamily17 module; only call its SMN read entrypoint.
        struct { char function[32];int64_t address; } input={"ioctl_read_smn",0x59800};
        int64_t output=0;DWORD got=0;
        if(DeviceIoControl(driver,(41394u<<16)|(0x841u<<2),&input,sizeof(input),&output,8,&got,NULL)&&got==8) {
            *raw=(uint32_t)output;
            if(*raw&&*raw!=0xffffffffu) {
                *temperature=decode(*raw);
                if(*temperature>0&&*temperature<=150)status=OK;
            }
        }
    } else if(read_pci(driver,0,&host)&&(host&0xffff)==0x1022&&read_pci(driver,0x60,&old)) {
        selected=select_smn(driver,0x59800);
        if(selected&&read_pci(driver,0x64,raw)&&*raw!=0&&*raw!=0xffffffffu) {
            *temperature=decode(*raw);
            if(*temperature>0&&*temperature<=150)status=OK;
        }
        // Restore even after a failed data read, BEFORE releasing the PCI mutex.
        if(!select_smn(driver,old))status=READ_FAILED;
    }
    last_error=status==READ_FAILED?GetLastError():0;sample_count++;
    ReleaseMutex(mutex);return status;
}
static HANDLE open_ring(unsigned *status) {
    HANDLE h=CreateFileW(L"\\\\.\\WinRing0_1_2_0",GENERIC_READ|GENERIC_WRITE,
                        0,NULL,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,NULL);
    last_error=h==INVALID_HANDLE_VALUE?GetLastError():0;
    *status=h!=INVALID_HANDLE_VALUE?OK:last_error==ERROR_ACCESS_DENIED?DENIED:
            last_error==ERROR_FILE_NOT_FOUND||last_error==ERROR_PATH_NOT_FOUND?NO_DRIVER:
            last_error==ERROR_SHARING_VIOLATION||last_error==ERROR_LOCK_VIOLATION?BUSY:READ_FAILED;
    return h;
}
static HANDLE open_pawn(unsigned *status) {
    HANDLE h=CreateFileW(L"\\\\?\\GLOBALROOT\\Device\\PawnIO",GENERIC_READ|GENERIC_WRITE,
                        FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,NULL);
    last_error=h==INVALID_HANDLE_VALUE?GetLastError():0;
    *status=h!=INVALID_HANDLE_VALUE?OK:(last_error==ERROR_ACCESS_DENIED?DENIED:NO_DRIVER);
    return h;
}
static int local_file(const wchar_t *file,wchar_t *path) {
    DWORD n=GetModuleFileNameW(NULL,path,32768);if(!n||n>=32768)return 0;
    wchar_t *end=wcsrchr(path,L'\\');if(!end)return 0;
    *(end+1)=0;if(wcslen(path)+wcslen(file)>=32768)return 0;wcscat(path,file);return 1;
}
static void *checked_file(const wchar_t *file,const char *expected,DWORD *size) {
    wchar_t path[32768];if(!local_file(file,path))return NULL;
    HANDLE h=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,0,NULL);
    if(h==INVALID_HANDLE_VALUE)return NULL;
    DWORD len=GetFileSize(h,NULL),got=0;if(!len||len>16000000){CloseHandle(h);return NULL;}
    void *buf=malloc(len);if(!buf){CloseHandle(h);return NULL;}
    int ok=ReadFile(h,buf,len,&got,NULL)&&got==len;CloseHandle(h);
    BCRYPT_ALG_HANDLE alg=NULL;BCRYPT_HASH_HANDLE state=NULL;unsigned char hash[32];char hex[65]={0};
    if(ok&&BCryptOpenAlgorithmProvider(&alg,BCRYPT_SHA256_ALGORITHM,NULL,0)==0) {
        ok=BCryptCreateHash(alg,&state,NULL,0,NULL,0,0)==0;
        if(ok)ok=BCryptHashData(state,buf,len,0)==0&&BCryptFinishHash(state,hash,32,0)==0;
        if(state)BCryptDestroyHash(state);BCryptCloseAlgorithmProvider(alg,0);
        for(int i=0;i<32;i++)sprintf(hex+2*i,"%02x",hash[i]);
        ok=ok&&!strcmp(hex,expected);
    } else ok=0;
    if(!ok){free(buf);return NULL;}*size=len;return buf;
}
static int load_pawn(HANDLE driver) {
    DWORD size=0,got=0;
    void *bin=checked_file(L"AMDFamily17.bin","dae74615761b78bdf064dfb3e136252ddcc6fc727d88f14738d0e5800d427a91",&size);
    if(!bin)return 0;
    int ok=DeviceIoControl(driver,(41394u<<16)|(0x821u<<2),bin,size,NULL,0,&got,NULL);
    free(bin);return ok;
}
static unsigned install_pawn(void) {
    DWORD size=0;
    void *bytes=checked_file(L"PawnIO_setup.exe","1f519a22e47187f70a1379a48ca604981c4fcf694f4e65b734aaa74a9fba3032",&size);
    if(!bytes)return PACKAGE_ERROR;free(bytes);
    wchar_t path[32768],command[32790];if(!local_file(L"PawnIO_setup.exe",path))return PACKAGE_ERROR;
    swprintf(command,32790,L"\"%ls\" -install -silent",path);
    STARTUPINFOW startup={0};startup.cb=sizeof(startup);startup.dwFlags=STARTF_USESHOWWINDOW;startup.wShowWindow=SW_HIDE;
    PROCESS_INFORMATION pi={0};
    if(!CreateProcessW(path,command,NULL,NULL,FALSE,CREATE_NO_WINDOW,NULL,NULL,&startup,&pi))return READ_FAILED;
    DWORD wait=WaitForSingleObject(pi.hProcess,60000),code=ERROR_TIMEOUT;
    if(wait==WAIT_OBJECT_0)GetExitCodeProcess(pi.hProcess,&code);
    CloseHandle(pi.hThread);CloseHandle(pi.hProcess);last_error=code;
    return code==0?OK:code==3010?REBOOT:READ_FAILED;
}
static int start_existing_pawn(void) {
    SC_HANDLE scm=OpenSCManagerW(NULL,NULL,SC_MANAGER_CONNECT);if(!scm)return 0;
    SC_HANDLE service=OpenServiceW(scm,L"PawnIO",SERVICE_START|SERVICE_QUERY_STATUS);
    int present=service!=NULL;
    if(service) {
        SERVICE_STATUS s;
        if(QueryServiceStatus(service,&s)&&s.dwCurrentState==SERVICE_STOPPED)StartServiceW(service,0,NULL);
        CloseServiceHandle(service);
    }
    CloseServiceHandle(scm);return present;
}
static HANDLE prepare_driver(Snapshot *s,HANDLE parent,unsigned *status) {
    // Driver preparation is serialized across HaloStudio helper instances.
    HANDLE gate=CreateMutexW(NULL,FALSE,L"Global\\HaloStudioCpu.DriverPreparation");
    if(!gate){*status=DENIED;return INVALID_HANDLE_VALUE;}
    DWORD lock=WaitForSingleObject(gate,65000);
    HANDLE h=INVALID_HANDLE_VALUE;
    if(lock!=WAIT_OBJECT_0&&lock!=WAIT_ABANDONED){*status=BUSY;CloseHandle(gate);return h;}
    h=open_ring(status);
    if(h!=INVALID_HANDLE_VALUE){backend=1;reused=1;goto done;}
    if(*status!=NO_DRIVER)goto done;
    h=open_pawn(status);
    if(h!=INVALID_HANDLE_VALUE){backend=2;reused=1;goto module;}
    if(*status!=NO_DRIVER)goto done;
    if(start_existing_pawn()) {
        for(int i=0;i<10&&h==INVALID_HANDLE_VALUE;i++){Sleep(100);h=open_pawn(status);}
        if(h!=INVALID_HANDLE_VALUE){backend=2;reused=1;goto module;}
        goto done; // An installed but failing driver is reported, never reinstalled.
    }
    // Recheck WinRing0 before installing in case another monitor started it.
    h=open_ring(status);
    if(h!=INVALID_HANDLE_VALUE){backend=1;reused=1;goto done;}
    if(*status!=NO_DRIVER)goto done;
    if(s->stop||WaitForSingleObject(parent,0)!=WAIT_TIMEOUT){*status=STOPPED;goto done;}
    *status=install_pawn();if(*status!=OK)goto done;
    h=open_pawn(status);if(h==INVALID_HANDLE_VALUE)goto done;backend=2;reused=0;
module:
    if(!load_pawn(h)){CloseHandle(h);h=INVALID_HANDLE_VALUE;*status=PACKAGE_ERROR;}
done:
    ReleaseMutex(gate);CloseHandle(gate);return h;
}
static void publish(Snapshot *s,unsigned status,uint32_t raw,float temperature) {
    InterlockedIncrement(&s->sequence);MemoryBarrier();
    s->status=status;s->raw=raw;s->temperature=temperature;s->family=family;s->model=model;
    s->stamp=GetTickCount64();s->helper=GetCurrentProcessId();MemoryBarrier();
    s->backend=backend;s->reused=reused;s->samples=sample_count;s->error=last_error;MemoryBarrier();
    InterlockedIncrement(&s->sequence);
}
int main(int argc,char **argv) {
    int supported=cpu_supported();
    if(argc==2&&!strcmp(argv[1],"--self-test")) {
        brand[0]=0;
        uint32_t tests[]={432u<<21,(824u<<21)|0x80000,(824u<<21)|0x30000,0,0xffffffff};
        printf("[");for(int i=0;i<5;i++)printf("%s%.3f",i?",":"",decode(tests[i]));printf("]\n");return 0;
    }
    if(argc==2&&!strcmp(argv[1],"--probe")) {
        unsigned status=UNSUPPORTED;HANDLE driver=INVALID_HANDLE_VALUE;
        if(supported)driver=open_ring(&status);
        if(supported&&status==NO_DRIVER)driver=open_pawn(&status);
        if(driver!=INVALID_HANDLE_VALUE)CloseHandle(driver);
        printf("{\"supported\":%s,\"family\":%u,\"model\":%u,\"status\":%u}\n",
               supported?"true":"false",family,model,status);return 0;
    }
    if(argc!=3)return 2;
    char *end=NULL;unsigned long pid=strtoul(argv[1],&end,10);
    if(!pid||*end||strlen(argv[2])!=32)return 2;
    for(int i=0;i<32;i++)if(!((argv[2][i]>='0'&&argv[2][i]<='9')||(argv[2][i]>='a'&&argv[2][i]<='f')))return 2;
    char name[128];snprintf(name,sizeof(name),"Local\\HaloStudioCpu-%lu-%s",pid,argv[2]);
    HANDLE mapping=OpenFileMappingA(FILE_MAP_READ|FILE_MAP_WRITE,FALSE,name);
    if(!mapping)return 3;
    Snapshot *s=MapViewOfFile(mapping,FILE_MAP_READ|FILE_MAP_WRITE,0,0,sizeof(Snapshot));
    if(!s||memcmp(s->magic,"HALOTC02",8)||s->version!=2||s->parent!=pid)return 3;
    strncat(name,"-request",sizeof(name)-strlen(name)-1);
    HANDLE event=OpenEventA(SYNCHRONIZE,FALSE,name);
    HANDLE parent=OpenProcess(SYNCHRONIZE,FALSE,(DWORD)pid);
    HANDLE mutex=CreateMutexW(NULL,FALSE,L"Global\\Access_PCI");
    if(!mutex)mutex=OpenMutexW(SYNCHRONIZE|MUTEX_MODIFY_STATE,FALSE,L"Global\\Access_PCI");
    HANDLE driver=INVALID_HANDLE_VALUE;unsigned status=STARTING;
    if(!event||!parent||!mutex){publish(s,GetLastError()==ERROR_ACCESS_DENIED?DENIED:READ_FAILED,0,0);goto cleanup;}
    publish(s,PREPARING,0,0);
    if(s->stop||WaitForSingleObject(parent,0)!=WAIT_TIMEOUT){publish(s,STOPPED,0,0);goto cleanup;}
    if(supported)driver=prepare_driver(s,parent,&status);else status=UNSUPPORTED;
    publish(s,status,0,0);
    // Failed preparation ends this instance so the UI can explicitly retry.
    if(driver==INVALID_HANDLE_VALUE)goto cleanup;
    HANDLE waits[]={parent,event};
    while(WaitForMultipleObjects(2,waits,FALSE,INFINITE)==WAIT_OBJECT_0+1) {
        if(s->stop)break;
        uint32_t raw=0;float t=0;
        if(!supported)status=UNSUPPORTED;
        else {
            if(driver!=INVALID_HANDLE_VALUE)status=sample(driver,mutex,&raw,&t);
        }
        publish(s,status,raw,t);
    }
    publish(s,STOPPED,0,0);
cleanup:
    if(driver!=INVALID_HANDLE_VALUE)CloseHandle(driver);
    if(mutex)CloseHandle(mutex);if(parent)CloseHandle(parent);if(event)CloseHandle(event);
    UnmapViewOfFile(s);CloseHandle(mapping);return 0;
}
