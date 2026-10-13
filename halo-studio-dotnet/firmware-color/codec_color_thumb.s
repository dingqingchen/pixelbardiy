// HPL2 extension, called only after lease/SID/parser bounds validation.
// Entries: begin, data, tick, reset. Preserves AAPCS saved registers.
// EX 0x20001358..0x200013b8 (96 bytes); OLD 0x200013b8..0x200017b8.
// Both entirely inside exclusively-owned original upload workspace.
// Animation 1/2: lyric viewport; 3/4: full screen; 5: local character rain.
// No new RAM allocation, ISR, flash writer, or parser entry.
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
    // Config RGB remains untouched throughout the lease. Restoring it also on
    // acquisition avoids trusting uninitialized shared upload-workspace bytes.
    push {r4, lr}
    ldr r3, =0x20002a04
    ldrb r0, [r3, #0x12]
    ldrb r1, [r3, #0x13]
    ldrb r2, [r3, #0x14]
    bl write_color
    ldr r0, =EX
    movs r1, #0
    movs r2, #24
reset_loop:
    str r1, [r0], #4
    subs r2, #1
    bne reset_loop
    pop {r4, pc}

// Word 13 is pending RGB with a presence bit; word 14 is last committed RGB.
// Reuse the stock color writer and existing brightness, never settings/Flash.
commit_color:
    push {r4, lr}
    ldr r4, =EX
    ldr r0, [r4, #52]
    cmp r0, #0
    beq color_done
    ldr r1, [r4, #56]
    cmp r0, r1
    beq color_done
    str r0, [r4, #56]
    ubfx r1, r0, #8, #8
    ubfx r2, r0, #16, #8
    uxtb r0, r0
    bl write_color
color_done:
    pop {r4, pc}
write_color:
    push {r4, lr}
    ldr r3, =0x20002a04
    ldrb r3, [r3, #0x11]
    cmp r3, #100
    bls brightness_ok
    movs r3, #100
brightness_ok:
    ldr r4, =0x0800998d
    blx r4
    ldr r4, =0x080099cb
    blx r4
    pop {r4, pc}

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
    beq begin_size_ok
    cmp r1, #15
    bne reject
begin_size_ok:
    ldrb r0, [r4, #31]
    cmp r0, #0
    bne reject
    ldrb r0, [r4, #28]
    cmp r0, #2
    bhi reject
    ldrb r0, [r4, #29]
    cmp r0, #7
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
    uxth r1, r1
    cmp r1, #0
    bne frame_sequence_ready
    movs r1, #1
frame_sequence_ready:
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
    movs r0, #0
    str r0, [r5, #52]
    ldrb r0, [r4, #27]
    cmp r0, #15
    bne no_pending_color
    ldrb r0, [r4, #40]
    ldrb r1, [r4, #41]
    orr r0, r0, r1, lsl #8
    ldrb r1, [r4, #42]
    orr r0, r0, r1, lsl #16
    orr r0, r0, #0x01000000
    str r0, [r5, #52]
no_pending_color:
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
    // Commit RGB only after the full decompressed target has passed CRC.
    bl commit_color
    ldr r0, [r5, #36]
    cmp r0, #0
    beq direct_commit
    cmp r0, #5
    beq start_animation
    ldr r0, [r5, #28]
    cmp r0, #0
    beq direct_commit
start_animation:
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
    movs r6, #24
    ldr r2, [r4, #36]
    cmp r2, #3
    blo step_loop
    movs r6, #32
    cmp r2, #5
    bne step_loop
    movs r6, #160
step_loop:
    cmp r0, r1
    blo step_ready
    subs r0, r0, r1
    adds r5, #1
    cmp r5, r6
    blo step_loop
    bl finish_animation
    b anim_return
step_ready:
    ldr r0, [r4, #48]
    cmp r0, r5
    beq anim_return
    str r5, [r4, #48]
    ldr r0, [r4, #36]
    cmp r0, #5
    beq rain_setup
    // Old modes keep target decorations; full modes replace every column.
    ldr r0, =0x200017f0
    ldr r1, =0x20001bf0
    movw r2, #1024
    ldr r3, =0x08004ee9
    blx r3
    movs r6, #38
    movs r0, #238
    ldr r1, [r4, #36]
    cmp r1, #3
    blo geometry_ready
    movs r6, #0
    movw r0, #256
geometry_ready:
    str r0, [sp]
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
    cmp r1, #3
    bhs full_column
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
    b column_store
full_column:
    cmp r1, #6
    beq center_reveal
    cmp r1, #7
    beq dissolve
    cmp r1, #4
    beq full_wipe
    // Register shift by 32 yields zero, including step 0 without a special case.
    lsr.w r2, r2, r5
    rsb r1, r5, #32
    lsl.w r0, r0, r1
    orrs r0, r2
    b column_store
full_wipe:
    lsl r1, r5, #3
    cmp r6, r1
    blo column_store
    mov r0, r2
    b column_store
center_reveal:
    // Symmetric curtain: retain every old column until the center reaches it.
    sub r1, r6, #128
    cmp r1, #0
    bge center_distance
    mvns r1, r1
center_distance:
    lsl r3, r5, #2
    cmp r1, r3
    blo column_store
    mov r0, r2
    b column_store
dissolve:
    // Ordered 8x4 threshold tile, scrambled columns to avoid moving stripes.
    // Four mask bits repeated down the column; no pixel-sized scratch buffer.
    mov r10, r0
    mov r11, r2
    and r3, r6, #7
    eor r3, r3, r3, lsr #1
    lsls r3, #2
    movs r12, #0
    movs r2, #0
dissolve_bit:
    eor r1, r2, r2, lsr #1
    adds r1, r3, r1
    cmp r1, r5
    bhs dissolve_next
    movs r1, #1
    lsl.w r1, r1, r2
    orr r12, r12, r1
dissolve_next:
    adds r2, #1
    cmp r2, #4
    blo dissolve_bit
    ldr r1, =0x11111111
    mul r12, r12, r1
    and r0, r10, r12
    bic r2, r11, r12
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
    ldr r1, [sp]
    cmp r6, r1
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

// 32 independent five-pixel streams, one/two rows per tick; 3 glyph tail.
// Packed vertical glyphs avoid a framebuffer-sized scratch buffer or pixel loop.
// Steps 128..159 progressively reveal the accepted target from left to right.
rain_setup:
    ldr r7, =0x200017f0
    ldr r8, =rain_font
    movs r6, #0
rain_column:
    cmp r5, #128
    blo rain_glyph
    subs r0, r5, #128
    lsls r0, #3
    cmp r6, r0
    bhs rain_glyph
    ldr r0, =0x20001bf0
    bl column_read
    b rain_store
rain_glyph:
    movs r0, #0
    and r9, r6, #7
    cmp r9, #5
    bhs rain_store
    lsrs r3, r6, #3
    and r1, r3, #1
    adds r1, #1
    mul r10, r5, r1
    movs r1, #13
    mla r10, r3, r1, r10
    and r10, r10, #63
    sub r10, r10, #8
    rsb r11, r3, r3, lsl #3
    add r11, r11, r5, lsr #3
    mov.w r12, #0
rain_tail:
    add r3, r12, r12, lsl #1
    sub r3, r11, r3
    and r3, r3, #15
    add r3, r3, r3, lsl #2
    add r3, r8
    ldrb r1, [r3, r9]
    cmp r12, #0
    beq rain_solid
    // Monochrome panel: spatial density, not repeated blinking, dims the tail.
    tst r6, #1
    beq rain_even
    and r1, r1, #0x2a
    b rain_solid
rain_even:
    and r1, r1, #0x55
rain_solid:
    sub r2, r10, r12, lsl #3
    cmp r2, #0
    blt rain_negative
    cmp r2, #32
    bhs rain_next
    lsl.w r1, r1, r2
    orrs r0, r1
    b rain_next
rain_negative:
    rsbs r2, r2, #0
    cmp r2, #32
    bhs rain_next
    lsr.w r1, r1, r2
    orrs r0, r1
rain_next:
    add r12, r12, #1
    cmp r12, #3
    blo rain_tail
rain_store:
    adds r1, r7, r6
    strb r0, [r1]
    lsrs r0, #8
    strb r0, [r1, #256]
    lsrs r0, #8
    strb r0, [r1, #512]
    lsrs r0, #8
    strb r0, [r1, #768]
    adds r6, #1
    cmp r6, #256
    blo rain_column
    ldr r3, =0x08005203
    blx r3
    b anim_return
    .ltorg
    .align 2
rain_font:
    .byte 0x3e,0x51,0x49,0x45,0x3e
    .byte 0x00,0x42,0x7f,0x40,0x00
    .byte 0x42,0x61,0x51,0x49,0x46
    .byte 0x21,0x41,0x45,0x4b,0x31
    .byte 0x18,0x14,0x12,0x7f,0x10
    .byte 0x27,0x45,0x45,0x45,0x39
    .byte 0x3c,0x4a,0x49,0x49,0x30
    .byte 0x01,0x71,0x09,0x05,0x03
    .byte 0x7e,0x11,0x11,0x11,0x7e
    .byte 0x7f,0x49,0x49,0x49,0x41
    .byte 0x63,0x14,0x08,0x14,0x63
    .byte 0x61,0x51,0x49,0x45,0x43
    .byte 0x02,0x22,0x52,0x0f,0x02
    .byte 0x04,0x44,0x24,0x1f,0x04
    .byte 0x09,0x49,0x29,0x1f,0x09
    .byte 0x22,0x12,0x7f,0x12,0x02
