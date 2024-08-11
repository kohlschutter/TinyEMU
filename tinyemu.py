#!/usr/bin/env python3
import os, sys, subprocess, ctypes
from datetime import datetime

LIBTEMU = '/tmp/libtemu.so'
core = 'virtio.c pci.c fs.c cutils.c iomem.c simplefb.c elf.c'.split()
graphics = 'sdl.c vga.c softfp.c'.split()
machines = 'riscv_machine.c x86_cpu.c x86_machine.c'.split()
hardware = 'vmmouse.c ps2.c ide.c fs_disk.c pckbd.c'.split()

API = '''
#include <unistd.h>
#include <string.h>
#include <stdio.h>
#include <stdarg.h>

#include "cutils.h"
#include "iomem.h"
#include "virtio.h"
#include "machine.h"

void __attribute__((format(printf, 1, 2))) vm_error(const char *fmt, ...) {
	va_list ap;
	va_start(ap, fmt);
	vfprintf(stderr, fmt, ap);
	va_end(ap);
}

VirtMachine *vm;
#define MAX_EXEC_CYCLE 500000

void temu_iterate(){
	vm->vmc->virt_machine_interp(vm, MAX_EXEC_CYCLE);
}

void temu_load( const char *bios, int len ){
	printf("temu_load:\\n");
	VirtMachineParams _p;
	VirtMachineParams *p = &_p;

	memset(p, 0, sizeof(*p));

	p->machine_name = "riscv64";
	p->vmc = &riscv_machine_class;
	printf("vmc:%p\\n", p->vmc);
	printf("vmc->virt_machine_set_defaults:%p\\n", p->vmc->virt_machine_set_defaults);
	printf("vmc->virt_machine_init:%p\\n", p->vmc->virt_machine_init);
	p->vmc->virt_machine_set_defaults(p);
	p->ram_size = 100 << 20;
	p->files[VM_FILE_BIOS].filename = strdup("/bios");
	p->files[VM_FILE_BIOS].buf = malloc(len);
	p->files[VM_FILE_BIOS].len = len;
	memcpy(p->files[VM_FILE_BIOS].buf, bios, len);

	p->width = 320;
	p->height = 200;
	vm = p->vmc->virt_machine_init(p);
}
'''

def gen_api():
	tmp = '/tmp/tinyemu_api.c'
	open(tmp,'wb').write(API.encode('utf-8'))
	return tmp

def compile(c, output=None, defs=None):
	if output:
		assert c != output
		ofile = output
	else:
		ofile = c+'.o'
	cmd = [
		'gcc', '-g',
		'-I./',
		"-c",  ## do not call the linker
		"-fPIC",  ## position indepenent code
		'-DCONFIG_VERSION="%s"' % datetime.today().strftime('%Y-%m-%d'),
		'-DCONFIG_SDL', '-DCONFIG_RISCV_MAX_XLEN=128', 
		#'-DCONFIG_X86EMU', #'-DCONFIG_COMPRESSED_INITRAMFS',
		"-o", ofile, c,
	]
	if defs: cmd += defs
	print(cmd)
	subprocess.check_call(cmd)
	return ofile

def link(obs):
	cmd = ['gcc', '-shared', '-o', LIBTEMU] + obs + ['-lSDL2']
	print(cmd)
	subprocess.check_call(cmd)

def build():
	obs = [ compile(gen_api()) ]
	for arch in (32,64,128):
		obs.append( compile('riscv_cpu.c', output='/tmp/riscv_cpu%s.o'%arch, defs=['-DMAX_XLEN=%s' % arch]) )
	for c in core:
		obs.append(compile(c))
	for c in graphics:
		obs.append(compile(c))
	for c in machines:
		obs.append(compile(c))
	for c in hardware:
		obs.append(compile(c))
	print(obs)
	link(obs)

def test():
	elf = '/tmp/test.elf'
	for arg in sys.argv:
		if arg.endswith( ('.elf', '.bin') ): elf = arg
	dll = ctypes.CDLL(LIBTEMU)
	print(dll)
	print(dll.temu_load)
	dll.temu_load.argtypes = [ctypes.c_char_p, ctypes.c_int]
	elf = open(elf,'rb').read()
	dll.temu_load(elf, len(elf))
	while True:
		dll.temu_iterate()

if __name__=='__main__':
	build()
	test()
