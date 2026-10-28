using System.Diagnostics;

namespace HaloStudio;

internal static class DeviceOwnerTests
{
    public static void Run(Action<bool, string> assert)
    {
        string folder = Path.Combine(Path.GetTempPath(), "halostudio-owner-test-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(folder); string path = Path.Combine(folder, "owner.lock");
        void Record(int pid, string name, string extra = "") => File.WriteAllText(path, $"{pid}\n{name}\n{Environment.MachineName}\n\n\n{extra}\n");
        try
        {
            using (var owner = new DeviceOwner(path))
            {
                Record(int.MaxValue, "HaloStudioNet"); owner.Acquire();
                using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
                using (var reader = new StreamReader(stream))
                    assert(reader.ReadLine() == Environment.ProcessId.ToString(), "Dead owner record is replaced");
                bool denied = false;
                try { using var second = new DeviceOwner(path); second.Acquire(); } catch (IOException) { denied = true; }
                assert(denied, "A second owner cannot acquire an active display lock");
                denied = false; try { File.Delete(path); } catch (IOException) { denied = true; }
                assert(denied, "Live owner handle prevents stale cleanup from deleting its lock");
            }
            assert(!File.Exists(path), "Normal owner exit removes the lock");
            Record(Environment.ProcessId, "HaloStudioNet", "startUtcTicks=1");
            using (var owner = new DeviceOwner(path)) { owner.Acquire(); assert(true, "Reused PID with different process start time is recovered"); }
            using var other = Process.GetProcessesByName("svchost").First();
            Record(other.Id, "HaloStudioNet");
            using (var owner = new DeviceOwner(path)) { owner.Acquire(); assert(true, "Legacy PID reused by a Windows service does not block startup"); }
            Record(Environment.ProcessId, "HaloStudioNet");
            bool refused = false;
            try { using var owner = new DeviceOwner(path); owner.Acquire(); } catch (IOException) { refused = true; }
            assert(refused, "Live old C# owner remains protected without new metadata");
            File.Delete(path); Record(Environment.ProcessId, "python"); refused = false;
            try { using var owner = new DeviceOwner(path); owner.Acquire(); } catch (IOException) { refused = true; }
            assert(refused, "Live legacy Qt owner is not removed by C# cleanup");
        }
        finally { if (File.Exists(path)) File.Delete(path); Directory.Delete(folder); }
    }
}
