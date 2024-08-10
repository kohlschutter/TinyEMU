#!/usr/bin/env python3
import os, sys, subprocess, ctypes
from datetime import datetime

LIBTEMU = '/tmp/libtemu.so'
core = 'virtio.c pci.c fs.c cutils.c iomem.c simplefb.c json.c machine.c temu.c elf.c'.split()
graphics = 'sdl.c vga.c softfp.c'.split()
machines = 'riscv_machine.c x86_cpu.c x86_machine.c'.split()
hardware = 'vmmouse.c ps2.c ide.c fs_disk.c pckbd.c'.split()

def compile(c, output=None, defs=None):
	if output:
		assert c != output
		ofile = output
	else:
		ofile = c+'.o'
	cmd = [
		'gcc', '-g',
		"-c",  ## do not call the linker
		"-fPIC",  ## position indepenent code
		'-DCONFIG_VERSION="%s"' % datetime.today().strftime('%Y-%m-%d'),
		'-DCONFIG_SDL', '-DCONFIG_RISCV_MAX_XLEN=128', '-DCONFIG_X86EMU', 
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
	obs = []
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
	print(dll.main)

if __name__=='__main__':
	build()
	test()