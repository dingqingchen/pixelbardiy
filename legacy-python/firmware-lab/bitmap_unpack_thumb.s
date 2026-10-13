// OFFLINE ONLY. Template constants are substituted by validate_bitmap_space.py.
// Replacement for 0x0800519A: r0=original raw background address.
// Ten exact known background pointers are translated through a bounded directory.
// All other addresses keep the stock 1024-byte memcpy behavior. No Flash writes.
.syntax unified
.thumb
    push {r3-r7, lr}
    mov r4, r0
    ldr r0, =ASSET_BEGIN
    subs r1, r4, r0
    movw r2, #10240
    cmp r1, r2
    bhs raw_copy
    ubfx r2, r1, #0, #10
    cmp r2, #0
    bne bad
    lsrs r1, #10
    ldr r2, =DIRECTORY
    ldr.w r4, [r2, r1, lsl #2]
    adds r1, #1
    ldr.w r7, [r2, r1, lsl #2]
    ldr r0, =PACKED_BEGIN
    cmp r4, r0
    blo bad
    ldr r0, =PACKED_END
    cmp r7, r0
    bhi bad
    cmp r4, r7
    bhs bad
    ldr r5, =0x200017f0
    movw r6, #1024
next_token:
    cmp r6, #0
    beq complete
    cmp r4, r7
    bhs bad
    ldrb r0, [r4], #1
    and r1, r0, #127
    adds r1, #1
    cmp r1, r6
    bhi bad
    subs r6, r6, r1
    tst r0, #128
    beq literal
    cmp r4, r7
    bhs bad
    ldrb r2, [r4], #1
repeat:
    strb r2, [r5], #1
    subs r1, #1
    bne repeat
    b next_token
literal:
    adds r0, r4, r1
    cmp r0, r7
    bhi bad
literal_byte:
    ldrb r2, [r4], #1
    strb r2, [r5], #1
    subs r1, #1
    bne literal_byte
    b next_token
complete:
    cmp r4, r7
    bne bad
    pop {r0, r4-r7, pc}
bad:
    ldr r0, =0x200017f0
    movw r1, #1024
    movs r2, #0
clear:
    strb r2, [r0], #1
    subs r1, #1
    bne clear
    pop {r0, r4-r7, pc}
raw_copy:
    mov r1, r4
    ldr r0, =0x200017f0
    movw r2, #1024
    ldr r3, =0x08004ee9
    blx r3
    pop {r0, r4-r7, pc}
    .ltorg
