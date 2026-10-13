// OFFLINE INTEGRATION CANDIDATE. No hardware sender or installable image.
// Entry veneers: dispatch, service, timer, init, five scheduler gates, RX guard.
// State uses the last 32 bytes of the original 1200-byte upload workspace.
// Only an active validated lease lets the ISR update this shared workspace.
.syntax unified
.thumb
    b.w dispatch
    b.w service
    b.w timer
    b.w initialize
    b.w scheduler0
    b.w scheduler1
    b.w scheduler2
    b.w scheduler3
    b.w scheduler4
    b.w rx_guard
    b.w loop_guard
    b.w save_guard

active:
    ldr r1, =LEASE
    ldr r0, [r1]
    ldr r2, =0x324c5048
    cmp r0, r2
    bne inactive
    ldr r0, [r1, #4]
    mvns r2, r2
    cmp r0, r2
    bne inactive
    movs r0, #1
    bx lr
inactive:
    movs r0, #0
    bx lr

initialize:
    ldr r0, =LEASE
    movs r1, #0
    movs r2, #8
init_loop:
    str r1, [r0], #4
    subs r2, #1
    bne init_loop
    // Displaced original prologue at 0x08008BCE.
    push {r2-r10, lr}
    ldr r3, =0x08008bd3
    bx r3

timer:
    push {r4, lr}
    ldr r3, =0x0800a5e5
    blx r3
    bl active
    cmp r0, #0
    beq timer_done
    ldr r0, [r1, #8]
    adds r0, #1
    str r0, [r1, #8]
timer_done:
    pop {r4, pc}

poll:
    push {r4, lr}
    bl active
    cmp r0, #0
    beq poll_done
    ldr r0, [r1, #8]
    ldr r2, [r1, #12]
    subs r0, r0, r2
    movw r2, #2000
    cmp r0, r2
    blo poll_done
    bl release
poll_done:
    pop {r4, pc}
service:
    push {r4, lr}
    bl poll
    ldr r3, =0x08006bdd
    blx r3
    pop {r4, pc}

release:
    push {r4, lr}
    ldr r4, =LEASE
    ldr r0, [r4, #16]
    str r0, [r4, #24]
    movs r0, #0
    str r0, [r4]
    str r0, [r4, #4]
    ldr r1, =0x20001340
    movs r2, #3
    str r2, [r1, #12]
    ldr r1, =0x20002a04
    strb r0, [r1, #0x58]
    strb r0, [r1, #0x21]
    strb r0, [r1, #0x22]
    ldr r2, =0x20002af8
    str r0, [r2]
    movs r0, #2
    strb r0, [r1, #0x1c]
    ldr r3, =0x08002db5
    blx r3
    pop {r4, pc}

// Big-endian 32-bit read, safe for odd addresses. r0 in, r0 out.
be32:
    ldrb r1, [r0]
    ldrb r2, [r0, #1]
    orr.w r1, r2, r1, lsl #8
    ldrb r2, [r0, #2]
    orr.w r1, r2, r1, lsl #8
    ldrb r0, [r0, #3]
    orr.w r0, r0, r1, lsl #8
    bx lr

dispatch:
    push {r4-r8, lr}
    bl poll
    ldr r4, =0x200022e0
    ldr r5, =LEASE
    mov r0, r4
    bl be32
    ldr r1, =0x2b444959
    cmp r0, r1
    bne other_command
    adds r0, r4, #4
    bl be32
    ldr r1, =0x2b444154
    cmp r0, r1
    bne stock_diy
    // Every reserved high-bit sequence is consumed, even after lease release.
    ldrb r0, [r4, #13]
    tst r0, #128
    beq stock_diy
    cmp r0, #255
    bne handled
    ldrb r0, [r4, #14]
    cmp r0, #255
    bne handled
    ldrb r0, [r4, #8]
    cmp r0, #35
    bne handled
    ldrb r0, [r4, #9]
    cmp r0, #0
    bne handled
    ldrb r6, [r4, #10]
    cmp r6, #17
    blo handled
    cmp r6, #54
    bhi handled
    // Original parser has consumed exactly length+13 bytes before dispatch.
    adds r0, r4, r6
    ldrb r1, [r0, #11]
    cmp r1, #13
    bne handled
    ldrb r1, [r0, #12]
    cmp r1, #10
    bne handled
    adds r0, r4, #15
    bl be32
    ldr r1, =0x48504c32
    cmp r0, r1
    bne handled
    ldrb r8, [r4, #27]
    adds r0, r8, #17
    cmp r0, r6
    bne handled
    adds r0, r4, #20
    bl be32
    mov r7, r0
    cmp r7, #0
    beq handled
    ldrb r6, [r4, #19]
    cmp r6, #1
    beq acquire
    bl active
    cmp r0, #0
    beq handled
    ldr r0, [r5, #16]
    cmp r0, r7
    bne handled
    cmp r6, #4
    beq pixels
    cmp r8, #0
    bne handled
    cmp r6, #2
    beq heartbeat
    cmp r6, #3
    beq frame_begin
    cmp r6, #5
    bne handled
    bl release
    movs r0, #0x26
    b ack
acquire:
    cmp r8, #0
    bne handled
    bl active
    cmp r0, #0
    beq acquire_new
    ldr r0, [r5, #16]
    cmp r0, r7
    beq heartbeat
    b handled
acquire_new:
    ldr r0, [r5, #24]
    cmp r0, r7
    beq handled
    ldr r1, =0x20002a04
    ldrb r0, [r1, #0x1c]
    cmp r0, #0x5a
    beq handled
    ldrb r0, [r1, #0x58]
    cmp r0, #0
    bne handled
    movs r0, #0
    str r0, [r5, #8]
    str r0, [r5, #12]
    str r0, [r5, #20]
    str r7, [r5, #16]
    ldr r0, =0x324c5048
    mvns r1, r0
    str r1, [r5, #4]
    str r0, [r5]
    b heartbeat
frame_id:
    ldrb r0, [r4, #24]
    ldrb r1, [r4, #25]
    orr.w r0, r1, r0, lsl #8
    bx lr
frame_begin:
    bl frame_id
    ldr r1, [r5, #20]
    cmp r0, #0
    beq handled
    cmp r0, r1
    beq heartbeat
    adds r1, #1
    cmp r0, r1
    bne handled
    str r0, [r5, #20]
    ldr r0, =core_header
    ldr r1, [r5, #8]
    movs r2, #6
    ldr r3, =CORE_BEGIN
    blx r3
    b refresh_lease
pixels:
    bl frame_id
    cmp r0, #0
    beq handled
    ldr r1, [r5, #20]
    cmp r0, r1
    bne handled
    cmp r8, #0
    beq handled
    ldrb r6, [r4, #26]
    // Reframe in place AFTER validating SID/frame/length; parser owns RX buffer.
    movs r0, #0
    strb r0, [r4, #22]
    adds r1, r8, #4
    strb r1, [r4, #23]
    strb r0, [r4, #26]
    strb r6, [r4, #27]
    adds r0, r4, #22
    ldr r1, [r5, #8]
    adds r2, r8, #6
    ldr r3, =CORE_DATA
    blx r3
    cmp r0, #1
    bne handled
    b refresh_lease
heartbeat:
    movs r0, #0x25
    ldr r3, =0x08006c07
    blx r3
refresh_lease:
    ldr r0, [r5, #8]
    str r0, [r5, #12]
    b handled
ack:
    ldr r3, =0x08006c07
    blx r3
handled:
    movs r0, #1
    pop {r4-r8, pc}
stock_diy:
    bl active
    cmp r0, #0
    bne handled
    // Block the obsolete prototype's marked START even with no lease.
    ldrb r0, [r4, #11]
    tst r0, #128
    bne handled
    b forward
other_command:
    // Release before a legitimate power/reset/OTA-start path can change memory.
    ldr r1, =0x2b504f57
    cmp r0, r1
    beq release_forward
    ldr r1, =0x2b525354
    cmp r0, r1
    beq release_forward
    ldr r1, =0x2b4f5441
    cmp r0, r1
    bne whitelist
    adds r0, r4, #4
    bl be32
    ldr r1, =0x2b535441
    cmp r0, r1
    beq release_forward
    b stock_diy
whitelist:
    mov r6, r0
    bl active
    cmp r0, #0
    beq forward
    ldr r0, =0x2b434f4d
    cmp r6, r0
    beq forward
    ldr r0, =0x2b54494d
    cmp r6, r0
    beq forward
    ldr r0, =0x2b424154
    cmp r6, r0
    beq forward
    ldr r0, =0x2b564f4c
    cmp r6, r0
    beq forward
    ldr r0, =0x2b4c4544
    cmp r6, r0
    beq forward
    b handled
release_forward:
    bl active
    cmp r0, #0
    beq forward
    bl release
forward:
    pop {r4-r8, lr}
    ldr r3, =0x0800694d
    bx r3

scheduler0:
    push {r4, lr}
    ldr r4, =0x0800a2db
    b scheduler_gate
scheduler1:
    push {r4, lr}
    ldr r4, =0x0800a31f
    b scheduler_gate
scheduler2:
    push {r4, lr}
    ldr r4, =0x0800a35b
    b scheduler_gate
scheduler3:
    push {r4, lr}
    ldr r4, =0x0800a3ad
    b scheduler_gate
scheduler4:
    push {r4, lr}
    ldr r4, =0x0800a3d3
scheduler_gate:
    bl active
    cmp r0, #0
    bne skip_render
    mov r3, r4
    pop {r4, lr}
    bx r3
skip_render:
    pop {r4, pc}

save_guard:
    push {r4, lr}
    bl active
    cmp r0, #0
    beq save_stock
    // The caller just cleared its pending-save counter. Defer, don't lose it.
    ldr r1, =0x20002a35
    movs r0, #255
    strb r0, [r1]
    pop {r4, pc}
save_stock:
    pop {r4, lr}
    ldr r3, =0x0800919d
    bx r3

loop_guard:
    push {r0-r3, lr}
    sub sp, #4
    bl poll
    bl active
    cmp r0, #0
    beq loop_stock
    add sp, #4
    pop {r0-r3, lr}
    ldr r3, =0x08008c7f
    bx r3
loop_stock:
    add sp, #4
    pop {r0-r3, lr}
    ldr r5, =0x20002af8
    ldr r0, [r5]
    ldr r3, =0x08008bf9
    bx r3

// Guard only the new DIY transport and commands received during a lease.
// Preserve legacy OTA parser behavior outside a lease; not a general parser fix.
rx_guard:
    push {r2, r3}
    cmp r0, #4
    blo rx_store
    ldr r2, [r5]
    ldr r3, =0x5949442b
    cmp r2, r3
    bne rx_check_lease
    cmp r0, #67
    bhs rx_reject
    b rx_store
rx_check_lease:
    ldr r2, =LEASE
    ldr r3, [r2]
    ldr r2, =0x324c5048
    cmp r3, r2
    bne rx_store
    cmp r0, #400
    bhs rx_reject
rx_store:
    pop {r2, r3}
    strb r4, [r5, r0]
    ldrh r0, [r1]
    ldr r3, =0x08008873
    bx r3
rx_reject:
    pop {r2, r3}
    strh r2, [r1]
    movs r0, #0
    ldr r3, =0x20002b51
    strb r0, [r3]
    ldr r3, =0x080087bf
    bx r3
    .align 2
core_header:
    .byte 0,4,128,0,4,2
    .align 2
    .ltorg
