// HPL2 extension, called only after lease/SID/parser bounds validation.
// Entries: begin, data, tick, reset. Preserves AAPCS saved registers.
// EX 0x20001358..0x200013b8 (96 bytes); OLD 0x200013b8..0x200017b8.
// Both entirely inside exclusively-owned original upload workspace.
.syntax unified
.thumb
    b.w ext_begin
    b.w ext_data
    b.w anim_tick
    b.w ext_reset

// State words: status, out, encoded_remaining, next_index, run_remaining,
// run_kind, target_crc, committed_id, codec, animation, interval, start, step.
// status 0 idle, 1 receiving, 2 animating, 3 complete, 4 invalid.
ext_reset:
    ldr r0, =EX
    movs r1, #0
    movs r2, #24
reset_loop:
    str r1, [r0], #4
    subs r2, #1
    bne reset_loop
    bx lr

// Read network uint16 (unaligned-safe).
be16:
    ldrb r1, [r0]
    ldrb r0, [r0, #1]
    orr.w r0, r0, r1, lsl #8
    bx lr

crc_frame:
    push {r4-r6, lr}
    movs r4, #0
    movw r5, #1024
    movw r6, #0x1021
crc_byte:
    ldrb r1, [r0], #1
    eor.w r4, r4, r1, lsl #8
    movs r2, #8
crc_bit:
    lsls r4, #1
    tst.w r4, #0x10000
    beq crc_skip
    eors r4, r6
crc_skip:
    uxth r4, r4
    subs r2, #1
    bne crc_bit
    subs r5, #1
    bne crc_byte
    mov r0, r4
    pop {r4-r6, pc}

// Complete any accepted animation before beginning a new transfer.
finish_animation:
    push {r4, lr}
    ldr r4, =EX
    ldr r0, [r4]
    cmp r0, #2
    bne finish_return
    bl publish
    movs r0, #3
    str r0, [r4]
finish_return:
    pop {r4, pc}
publish:
    push {r4, lr}
    ldr r0, =0x200017f0
    ldr r1, =0x20001bf0
    movw r2, #1024
    ldr r3, =0x08004ee9
    blx r3
    ldr r3, =0x08005203
    blx r3
    pop {r4, pc}

// r0 = validated RX header base, r1 = payload length (12 required).
ext_begin:
    push {r4-r8, lr}
    mov r4, r0
    ldr r5, =EX
    cmp r1, #12
    bne reject
    ldrb r0, [r4, #31]
    cmp r0, #0
    bne reject
    ldrb r0, [r4, #28]
    cmp r0, #2
    bhi reject
    ldrb r0, [r4, #29]
    cmp r0, #2
    bhi reject
    ldrb r0, [r4, #30]
    cmp r0, #8
    blo reject
    cmp r0, #64
    bhi reject
    adds r0, r4, #32
    bl be16
    cmp r0, #0
    beq reject
    movw r1, #1032
    cmp r0, r1
    bhi reject
    mov r7, r0
    ldr r6, =LEASE
    adds r0, r4, #24
    bl be16
    mov r8, r0
    ldr r1, [r6, #20]
    adds r1, #1
    cmp r0, r1
    bne reject
    bl finish_animation
    ldrb r0, [r4, #28]
    cmp r0, #2
    bne keyframe_base
    adds r0, r4, #34
    bl be16
    cmp r0, #0
    beq reject
    ldr r1, [r5, #28]
    cmp r0, r1
    bne reject
    ldr r0, =0x200017f0
    bl crc_frame
    mov r6, r0
    adds r0, r4, #36
    bl be16
    cmp r0, r6
    bne reject
    b begin_valid
keyframe_base:
    adds r0, r4, #34
    bl be16
    cmp r0, #0
    bne reject
    adds r0, r4, #36
    bl be16
    cmp r0, #0
    bne reject
begin_valid:
    movs r0, #1
    str r0, [r5]
    movs r0, #0
    str r0, [r5, #4]
    str r0, [r5, #12]
    str r0, [r5, #16]
    str r0, [r5, #20]
    str r7, [r5, #8]
    ldrb r0, [r4, #28]
    str r0, [r5, #32]
    ldrb r0, [r4, #29]
    str r0, [r5, #36]
    ldrb r0, [r4, #30]
    str r0, [r5, #40]
    adds r0, r4, #38
    bl be16
    str r0, [r5, #24]
    ldr r6, =LEASE
    str r8, [r6, #20]
    // Prevent interleaved legacy DATA from committing stale staging bytes.
    ldr r1, =0x20001340
    movs r0, #3
    str r0, [r1, #12]
    movs r0, #0x25
    b send_ack
reject:
    movs r0, #0
    pop {r4-r8, pc}

// r0 validated RX base, r1 data length 1..37; frame/SID checked by dispatcher.
ext_data:
    push {r4-r8, lr}
    mov r4, r0
    ldr r5, =EX
    ldr r0, [r5]
    cmp r0, #1
    bne reject
    cmp r1, #0
    beq bad_data
    cmp r1, #37
    bhi bad_data
    ldrb r0, [r4, #26]
    ldr r2, [r5, #12]
    cmp r0, r2
    bne bad_data
    adds r2, #1
    str r2, [r5, #12]
    ldr r2, [r5, #8]
    cmp r1, r2
    bhi bad_data
    subs r2, r2, r1
    str r2, [r5, #8]
    adds r4, #28
    adds r6, r4, r1
    ldr r7, =0x20001bf0
    ldr r8, [r5, #4]
decode_loop:
    cmp r4, r6
    beq packet_done
    ldrb r0, [r4], #1
    ldr r1, [r5, #32]
    cmp r1, #0
    beq raw_byte
    ldr r1, [r5, #20]
    cmp r1, #0
    bne decode_value
    and r1, r0, #127
    adds r1, #1
    str r1, [r5, #16]
    movs r1, #1
    tst r0, #128
    beq token_ready
    movs r1, #2
token_ready:
    str r1, [r5, #20]
    b decode_loop
decode_value:
    cmp r1, #2
    beq repeated
    bl output_byte
    cmp r0, #0
    beq bad_data
    ldr r1, [r5, #16]
    subs r1, #1
    str r1, [r5, #16]
    bne decode_loop
    str r1, [r5, #20]
    b decode_loop
repeated:
    // Preserve the source byte across each XOR output, including 128-byte runs.
    mov r3, r0
repeat_loop:
    mov r0, r3
    bl output_byte
    cmp r0, #0
    beq bad_data
    ldr r1, [r5, #16]
    subs r1, #1
    str r1, [r5, #16]
    bne repeat_loop
    str r1, [r5, #20]
    b decode_loop
raw_byte:
    bl output_byte
    cmp r0, #0
    beq bad_data
    b decode_loop
packet_done:
    str r8, [r5, #4]
    ldr r0, [r5, #8]
    cmp r0, #0
    bne next_ack
    cmp r8, #1024
    bne bad_data
    ldr r0, [r5, #20]
    cmp r0, #0
    bne bad_data
    mov r0, r7
    bl crc_frame
    ldr r1, [r5, #24]
    cmp r0, r1
    bne bad_data
    ldr r0, [r5, #36]
    cmp r0, #0
    beq direct_commit
    ldr r0, [r5, #28]
    cmp r0, #0
    beq direct_commit
    ldr r0, =OLD
    ldr r1, =0x200017f0
    movw r2, #1024
    ldr r3, =0x08004ee9
    blx r3
    movs r0, #2
    str r0, [r5]
    ldr r0, =LEASE
    ldr r0, [r0, #8]
    str r0, [r5, #44]
    movs r0, #255
    str r0, [r5, #48]
    bl anim_tick
    b accepted
direct_commit:
    bl publish
    movs r0, #3
    str r0, [r5]
accepted:
    ldr r0, =LEASE
    ldr r0, [r0, #20]
    str r0, [r5, #28]
    movs r0, #0x26
    b send_ack
next_ack:
    movs r0, #0x25
send_ack:
    ldr r3, =0x08006c07
    blx r3
    movs r0, #1
    pop {r4-r8, pc}
bad_data:
    movs r0, #4
    str r0, [r5]
    b reject

// r0 decoded byte; r5 state, r7 stage, r8 offset. Keep r3 repeat value intact.
output_byte:
    cmp r8, #1024
    bhs output_bad
    ldr r1, [r5, #32]
    cmp r1, #2
    bne output_store
    ldr r1, =0x200017f0
    ldrb r1, [r1, r8]
    eors r0, r1
output_store:
    strb r0, [r7, r8]
    adds r8, #1
    movs r0, #1
    bx lr
output_bad:
    movs r0, #0
    bx lr

// Main-loop animation. No timer ISR drawing, no extra USB frames, no Flash.
anim_tick:
    push {r4-r11, lr}
    sub sp, #4
    ldr r4, =EX
    ldr r0, [r4]
    cmp r0, #2
    bne anim_return
    ldr r0, =LEASE
    ldr r0, [r0, #8]
    ldr r1, [r4, #44]
    subs r0, r0, r1
    ldr r1, [r4, #40]
    movs r5, #0
step_loop:
    cmp r0, r1
    blo step_ready
    subs r0, r0, r1
    adds r5, #1
    cmp r5, #24
    blo step_loop
    bl finish_animation
    b anim_return
step_ready:
    ldr r0, [r4, #48]
    cmp r0, r5
    beq anim_return
    str r5, [r4, #48]
    // Start with target decorations. Only x38..237, rows4..27 transition.
    ldr r0, =0x200017f0
    ldr r1, =0x20001bf0
    movw r2, #1024
    ldr r3, =0x08004ee9
    blx r3
    movs r6, #38
    ldr r7, =0x200017f0
    ldr r8, =OLD
    ldr r9, =0x20001bf0
    ldr r10, =0x00ffffff
    ldr r11, =0xf000000f
column_loop:
    mov r0, r8
    bl column_read
    mov r2, r0
    mov r0, r9
    bl column_read
    ldr r1, [r4, #36]
    cmp r1, #2
    beq wipe_column
    and r12, r0, r11
    lsrs r2, #4
    and r2, r2, r10
    lsr.w r2, r2, r5
    lsrs r0, #4
    and r0, r0, r10
    rsb r1, r5, #24
    lsl.w r0, r0, r1
    orrs r0, r2
    and r0, r0, r10
    lsl r0, r0, #4
    orr r0, r0, r12
    b column_store
wipe_column:
    lsl r1, r5, #3
    adds r1, #38
    cmp r6, r1
    blo column_store
    and r0, r0, r11
    bic r2, r2, r11
    orrs r0, r2
column_store:
    adds r1, r7, r6
    strb r0, [r1]
    lsrs r0, #8
    strb r0, [r1, #256]
    lsrs r0, #8
    strb r0, [r1, #512]
    lsrs r0, #8
    strb r0, [r1, #768]
    adds r6, #1
    cmp r6, #238
    blo column_loop
    ldr r3, =0x08005203
    blx r3
anim_return:
    add sp, #4
    pop {r4-r11, pc}
column_read:
    adds r1, r0, r6
    ldrb r0, [r1]
    ldrb r12, [r1, #256]
    orr r0, r0, r12, lsl #8
    ldrb r12, [r1, #512]
    orr r0, r0, r12, lsl #16
    ldrb r12, [r1, #768]
    orr r0, r0, r12, lsl #24
    bx lr
    .ltorg
