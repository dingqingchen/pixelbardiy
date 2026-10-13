"""Derive a separately reviewed extension; leave installed matrix source intact."""
from pathlib import Path
HERE = Path(__file__).resolve().parent
source = (HERE.parent / 'firmware-matrix/codec_matrix_thumb.s').read_text()
def patch(old, new):
    global source
    assert source.count(old) == 1, old
    source = source.replace(old, new)

# The session dispatcher and all installed hook addresses stay unchanged.
# BEGIN adds RGB only in its new exact 15-byte form. No new opcode or receiver.
patch('    cmp r1, #12\n    bne reject', '''    cmp r1, #12
    beq begin_size_ok
    cmp r1, #15
    bne reject
begin_size_ok:''')
patch('    cmp r0, #5\n    bhi reject', '    cmp r0, #7\n    bhi reject')
patch('    adds r1, #1\n    cmp r0, r1\n    bne reject', '''    adds r1, #1
    uxth r1, r1
    cmp r1, #0
    bne frame_sequence_ready
    movs r1, #1
frame_sequence_ready:
    cmp r0, r1
    bne reject''')
patch('begin_valid:\n', '''begin_valid:
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
''')
patch('    cmp r0, r1\n    bne bad_data\n    ldr r0, [r5, #36]', '''    cmp r0, r1
    bne bad_data
    // Commit RGB only after the full decompressed target has passed CRC.
    bl commit_color
    ldr r0, [r5, #36]''')
patch('ext_reset:\n', '''ext_reset:
    // Config RGB remains untouched throughout the lease. Restoring it also on
    // acquisition avoids trusting uninitialized shared upload-workspace bytes.
    push {r4, lr}
    ldr r3, =0x20002a04
    ldrb r0, [r3, #0x12]
    ldrb r1, [r3, #0x13]
    ldrb r2, [r3, #0x14]
    bl write_color
''')
patch('    bne reset_loop\n    bx lr', '    bne reset_loop\n    pop {r4, pc}')
patch('// Read network uint16 (unaligned-safe).', '''// Word 13 is pending RGB with a presence bit; word 14 is last committed RGB.
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

// Read network uint16 (unaligned-safe).''')
patch('full_column:\n    cmp r1, #4', '''full_column:
    cmp r1, #6
    beq center_reveal
    cmp r1, #7
    beq dissolve
    cmp r1, #4''')
patch('column_store:\n', '''    b column_store
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
''')
(HERE / 'codec_color_thumb.s').write_text(source, encoding='utf-8')
print('Derived color commit and center/dissolve transitions.')
