/* everything in one blob, entry (_start in .text.entry) at offset 0, no bss/relocations needed */
ENTRY(_start)
SECTIONS
{
    . = 0;
    .text : { *(.text.entry) *(.text .text.*) }
    .rodata : { *(.rodata .rodata.*) }
    .data : { *(.data .data.*) }
    .bss : { *(.bss .bss.*) *(COMMON) }
    /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) *(.interp) *(.dynsym) *(.dynstr) *(.hash) *(.gnu.hash) }
}
