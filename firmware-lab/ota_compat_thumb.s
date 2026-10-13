// Compatibility with the previously installed OTA first-byte filter.
// Two existing bitmap spans are XOR-encoded in the image and decoded only
// when drawn. Addresses and rendered pixels are unchanged; no Flash writes.
.syntax unified
.thumb
    b.w background
    b.w glyph
background:
    push {r4, lr}
    mov r4, r0
    ldr r3, =DECODER
    blx r3
    ldr r1, =0x0800eaec
    cmp r4, r1
    bne background_done
    ldr r1, =0x200018f0
    movw r2, #256
background_byte:
    ldrb r3, [r1]
    eor r3, r3, #128
    strb r3, [r1], #1
    subs r2, #1
    bne background_byte
background_done:
    pop {r4, pc}
glyph:
    // Replaces exactly: ldrb r0,[r5]; mov r8,r0.
    // Preserve flags and all other live registers in the original rasterizer.
    push {r1-r3}
    mrs r3, apsr
    ldrb r0, [r5]
    ldr r1, =0x0800f632
    subs r2, r5, r1
    cmp r2, #66
    bhs glyph_done
    eor r0, r0, #128
glyph_done:
    mov r8, r0
    msr apsr_nzcvq, r3
    pop {r1-r3}
    bx lr
    .align 2
    .ltorg
