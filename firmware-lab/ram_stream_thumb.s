// OFFLINE EXPERIMENT ONLY. Not linked into an installable firmware image.
// Four entry veneers: begin, data, end, gate. ARM Thumb-2 / AAPCS.
// begin/data: r0=length-prefixed MCU packet, r1=monotonic milliseconds,
//             r2=verified available span (including the two length bytes).
// Return 0=not our session, 1=handled, 2=invalid experimental transaction.
// gate: r0=milliseconds; returns 1 while experimental renderer owns the frame.
// Session magic is kept after abort to swallow late DAT/END packets safely.
// Actual firmware dispatch, time source, and RAM ownership are NOT integrated.

.syntax unified
.thumb
    b.w begin
    b.w data
    b.w end
    b.w gate

begin:
    push {r4-r6, lr}
    cmp r2, #6
    bne begin_fallback
    ldrb r3, [r0]
    cmp r3, #0
    bne begin_fallback
    ldrb r3, [r0, #1]
    cmp r3, #4
    bne begin_fallback
    ldrb r3, [r0, #2]
    cmp r3, #0x80
    bne begin_fallback
    ldrb r3, [r0, #3]
    cmp r3, #0
    bne begin_fallback
    ldrb r3, [r0, #4]
    cmp r3, #4
    bne begin_fallback
    ldrb r3, [r0, #5]
    cmp r3, #2
    bne begin_fallback
    ldr r4, =0x20001340
    ldr r3, =0x31584c50
    str r3, [r4]
    movs r3, #0
    str r3, [r4, #4]
    str r3, [r4, #12]
    str r3, [r4, #16]
    str r3, [r4, #20]
    str r1, [r4, #8]
    ldr r5, =0x20002a04
    ldrb r6, [r5, #0x1c]
    cmp r6, #3
    bne begin_bad
    strb r3, [r5, #0x58]
    movs r0, #0x24
    ldr r3, =0x08006c07
    blx r3
    movs r0, #1
    pop {r4-r6, pc}
begin_bad:
    movs r3, #3
    str r3, [r4, #12]
    movs r0, #2
    pop {r4-r6, pc}
begin_fallback:
    movs r0, #0
    pop {r4-r6, pc}

data:
    push {r4-r8, lr}
    ldr r4, =0x20001340
    ldr r3, [r4]
    ldr r5, =0x31584c50
    cmp r3, r5
    bne data_fallback
    ldr r3, [r4, #12]
    cmp r3, #3
    beq data_bad
    ldr r3, [r4, #8]
    subs r3, r1, r3
    movw r5, #2000
    cmp r3, r5
    bhi data_bad
    ldr r3, =0x20002a20
    ldrb r3, [r3]
    cmp r3, #3
    bne data_bad
    cmp r2, #7
    blo data_bad
    cmp r2, #56
    bhi data_bad
    ldrb r3, [r0]
    ldrb r5, [r0, #1]
    orr.w r3, r5, r3, lsl #8
    adds r3, #2
    cmp r3, r2
    bne data_bad
    ldrb r3, [r0, #4]
    ldrb r5, [r0, #5]
    orr.w r3, r5, r3, lsl #8
    ldrh r5, [r4, #6]
    cmp r3, r5
    bne duplicate
    ldr r3, [r4, #12]
    cmp r3, #0
    bne data_bad
    subs r6, r2, #6
    ldrh r7, [r4, #4]
    adds r3, r7, r6
    movw r5, #1026
    cmp r3, r5
    bhi data_bad
    str r7, [r4, #20]
    strh r6, [r4, #18]
    str r1, [r4, #8]
    adds r5, r0, #6
    ldr r8, =0x20001bf0
copy_chunk:
    ldrb r0, [r5], #1
    cmp r7, #1024
    bhs copy_crc
    strb r0, [r8, r7]
    b copy_next
copy_crc:
    subw r1, r7, #1008
    strb r0, [r4, r1]
copy_next:
    adds r7, #1
    subs r6, #1
    bne copy_chunk
    strh r7, [r4, #4]
    ldrh r0, [r4, #6]
    adds r0, #1
    strh r0, [r4, #6]
    movw r0, #1026
    cmp r7, r0
    bne data_next_ack
    movs r5, #0
    movs r6, #0
    movw r7, #0x1021
crc_byte:
    ldrb r0, [r8, r5]
    eor.w r6, r6, r0, lsl #8
    movs r1, #8
crc_bit:
    lsls r6, #1
    tst.w r6, #0x10000
    beq crc_no_xor
    eors r6, r7
crc_no_xor:
    uxth r6, r6
    subs r1, #1
    bne crc_bit
    adds r5, #1
    cmp r5, #1024
    bne crc_byte
    ldrh r0, [r4, #16]
    rev16 r0, r0
    cmp r0, r6
    bne data_bad
    ldr r0, =0x200017f0
    mov r1, r8
    movw r2, #1024
    ldr r3, =0x08004ee9
    blx r3
    ldr r3, =0x08005203
    blx r3
    movs r0, #2
    str r0, [r4, #12]
data_done_ack:
    movs r0, #0x26
    b data_ack
data_next_ack:
    movs r0, #0x25
data_ack:
    ldr r3, =0x08006c07
    blx r3
    movs r0, #1
    pop {r4-r8, pc}

duplicate:
    cmp r5, #0
    beq data_bad
    subs r5, #1
    cmp r3, r5
    bne data_bad
    subs r6, r2, #6
    ldrh r3, [r4, #18]
    cmp r6, r3
    bne data_bad
    ldr r7, [r4, #20]
    adds r5, r0, #6
    ldr r8, =0x20001bf0
duplicate_byte:
    ldrb r0, [r5], #1
    cmp r7, #1024
    bhs duplicate_crc
    ldrb r3, [r8, r7]
    b duplicate_compare
duplicate_crc:
    subw r2, r7, #1008
    ldrb r3, [r4, r2]
duplicate_compare:
    cmp r0, r3
    bne data_bad
    adds r7, #1
    subs r6, #1
    bne duplicate_byte
    str r1, [r4, #8]
    ldr r0, [r4, #12]
    cmp r0, #2
    beq data_done_ack
    b data_next_ack
data_bad:
    movs r0, #3
    str r0, [r4, #12]
    movs r0, #2
    pop {r4-r8, pc}
data_fallback:
    movs r0, #0
    pop {r4-r8, pc}

end:
    push {r4, lr}
    ldr r4, =0x20001340
    ldr r0, [r4]
    ldr r1, =0x31584c50
    cmp r0, r1
    bne end_fallback
    ldr r0, [r4, #12]
    cmp r0, #2
    bne end_bad
    movs r0, #0x26
    ldr r3, =0x08006c07
    blx r3
    movs r0, #1
    pop {r4, pc}
end_bad:
    movs r0, #3
    str r0, [r4, #12]
    movs r0, #2
    pop {r4, pc}
end_fallback:
    movs r0, #0
    pop {r4, pc}

gate:
    ldr r1, =0x20001340
    ldr r2, [r1]
    ldr r3, =0x31584c50
    cmp r2, r3
    bne gate_off
    ldr r2, [r1, #12]
    cmp r2, #3
    beq gate_off
    ldr r2, =0x20002a20
    ldrb r2, [r2]
    cmp r2, #3
    bne gate_abort
    ldr r2, [r1, #8]
    subs r0, r0, r2
    movw r3, #2000
    cmp r0, r3
    bhi gate_abort
    movs r0, #1
    bx lr
gate_abort:
    movs r2, #3
    str r2, [r1, #12]
gate_off:
    movs r0, #0
    bx lr
    .ltorg
