#!/usr/bin/env python3
import os, sys, subprocess, ctypes
from datetime import datetime

LIBTEMU = '/tmp/libtemu.so'
core = 'virtio.c pci.c fs.c cutils.c iomem.c simplefb.c json.c machine.c elf.c'.split()
graphics = 'sdl.c vga.c softfp.c'.split()
machines = 'riscv_machine.c x86_cpu.c x86_machine.c'.split()
hardware = 'vmmouse.c ps2.c ide.c fs_disk.c pckbd.c'.split()

API = '''
#include <unistd.h>
#include "cutils.h"
#include "iomem.h"
#include "virtio.h"
#include "machine.h"

VirtMachine *vm;

void temu_load( const char *path ){
	printf("temu_load:\\n");
	printf("path:%s\\n",path);
	VirtMachineParams _p;
	VirtMachineParams *p = &_p;

	virt_machine_set_defaults(p);

	p->machine_name = "riscv64";
	p->vmc = virt_machine_find_class(p->machine_name);
	if (!p->vmc) printf("ERROR: invalid machine type\\n");
	printf("vmc:%p\\n", p->vmc);
	p->vmc->virt_machine_set_defaults(p);
	printf("temu_load defaults OK:\\n");
	p->ram_size = 100 << 20;
	p->files[VM_FILE_BIOS].filename = strdup(path);
	p->width = 320;
	p->height = 200;
	printf("temu_load machine init:\\n");
	vm = virt_machine_init(p);
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
		#'-DCONFIG_X86EMU', 
		#'-DCONFIG_COMPRESSED_INITRAMFS',
		"-o",
		ofile,
		c,
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
	dll = ctypes.CDLL(LIBTEMU)
	print(dll)
	print(dll.temu_load)
	dll.temu_load.argtypes = [ctypes.c_char_p]
	dll.temu_load("hello world".encode('utf-8'))

if __name__=='__main__':
	build()
	test()
