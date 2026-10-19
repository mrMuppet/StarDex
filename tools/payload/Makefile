# Freestanding GoldHEN payload. Build in WSL/Linux: make
# Send dl0link.elf to port 9090 - GoldHEN's BinLoader rejects the raw dl0link.bin ("invalid payload format").
CFLAGS = -O2 -fPIE -ffreestanding -fno-builtin -nostdlib -fno-stack-protector -fno-asynchronous-unwind-tables \
         -fno-unwind-tables -mno-red-zone -fcf-protection=none -Wall -Wextra

dl0link.bin: dl0link.elf
	objcopy -O binary dl0link.elf $@

dl0link.elf: dl0link.c payload.ld
	gcc $(CFLAGS) -static-pie -T payload.ld -Wl,--no-dynamic-linker -Wl,-z,norelro -Wl,--build-id=none -o $@ dl0link.c

clean:
	rm -f dl0link.elf dl0link.bin
