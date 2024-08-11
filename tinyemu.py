#!/usr/bin/env python3
import os, sys, subprocess, ctypes
from datetime import datetime

LIBTEMU = '/tmp/libtemu.so'
core = 'virtio.c pci.c fs.c cutils.c iomem.c simplefb.c elf.c'.split()
graphics = 'sdl.c vga.c softfp.c'.split()
machines = 'riscv_machine.c'.split() # x86_cpu.c x86_machine.c
hardware = 'vmmouse.c ps2.c ide.c fs_disk.c pckbd.c'.split()

API_INC = '''
#include <stdlib.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <inttypes.h>
#include <assert.h>
#include <fcntl.h>
#include <errno.h>
#include <unistd.h>
#include <time.h>
#include <getopt.h>
#include <net/if.h>
#include <linux/if_tun.h>
#include <termios.h>
#include <signal.h>
#include "cutils.h"
#include "iomem.h"
#include "virtio.h"
#include "machine.h"
#include "fs_utils.h"
'''

API_CONSOLE = r'''
#include <fcntl.h>

typedef struct {
	int stdin_fd;
	int console_esc_state;
	BOOL resize_pending;
} STDIODevice;

static struct termios oldtty;
static int old_fd0_flags;
static STDIODevice *global_stdio_device;

static void term_exit(void){
	tcsetattr (0, TCSANOW, &oldtty);
	fcntl(0, F_SETFL, old_fd0_flags);
}

static void term_init(BOOL allow_ctrlc){
	struct termios tty;
	memset(&tty, 0, sizeof(tty));
	tcgetattr (0, &tty);
	oldtty = tty;
	old_fd0_flags = fcntl(0, F_GETFL);
	tty.c_iflag &= ~(IGNBRK|BRKINT|PARMRK|ISTRIP|INLCR|IGNCR|ICRNL|IXON);
	tty.c_oflag |= OPOST;
	tty.c_lflag &= ~(ECHO|ECHONL|ICANON|IEXTEN);
	if (!allow_ctrlc) tty.c_lflag &= ~ISIG;
	tty.c_cflag &= ~(CSIZE|PARENB);
	tty.c_cflag |= CS8;
	tty.c_cc[VMIN] = 1;
	tty.c_cc[VTIME] = 0;
	tcsetattr (0, TCSANOW, &tty);
	atexit(term_exit);
}

static void console_write(void *opaque, const uint8_t *buf, int len){
	fwrite(buf, 1, len, stdout);
	fflush(stdout);
}

static int console_read(void *opaque, uint8_t *buf, int len){
	STDIODevice *s = opaque;
	int ret, i, j;
	uint8_t ch;
	
	if (len <= 0)
		return 0;

	ret = read(s->stdin_fd, buf, len);
	if (ret < 0)
		return 0;
	if (ret == 0) {
		/* EOF */
		exit(1);
	}

	j = 0;
	for(i = 0; i < ret; i++) {
		ch = buf[i];
		if (s->console_esc_state) {
			s->console_esc_state = 0;
			switch(ch) {
			case 'x':
				printf("Terminated\n");
				exit(0);
			case 'h':
				printf("\n"
					   "C-a h   print this help\n"
					   "C-a x   exit emulator\n"
					   "C-a C-a send C-a\n"
					   );
				break;
			case 1:
				goto output_char;
			default:
				break;
			}
		} else {
			if (ch == 1) {
				s->console_esc_state = 1;
			} else {
			output_char:
				buf[j++] = ch;
			}
		}
	}
	return j;
}

static void term_resize_handler(int sig) {
	if (global_stdio_device) global_stdio_device->resize_pending = TRUE;
}

CharacterDevice *console_init(BOOL allow_ctrlc) {
	CharacterDevice *dev;
	STDIODevice *s;
	struct sigaction sig;
	term_init(allow_ctrlc);
	dev = mallocz(sizeof(*dev));
	s = mallocz(sizeof(*s));
	s->stdin_fd = 0;
	/* Note: the glibc does not properly tests the return value of
	   write() in printf, so some messages on stdout may be lost */
	fcntl(s->stdin_fd, F_SETFL, O_NONBLOCK);
	s->resize_pending = TRUE;
	global_stdio_device = s;
	/* use a signal to get the host terminal resize events */
	sig.sa_handler = term_resize_handler;
	sigemptyset(&sig.sa_mask);
	sig.sa_flags = 0;
	sigaction(SIGWINCH, &sig, NULL);
	dev->opaque = s;
	dev->write_data = console_write;
	dev->read_data = console_read;
	return dev;
}
'''


API_VM = '''
void __attribute__((format(printf, 1, 2))) vm_error(const char *fmt, ...) {
	va_list ap;
	va_start(ap, fmt);
	vfprintf(stderr, fmt, ap);
	va_end(ap);
}

VirtMachine *vm;
#define MAX_EXEC_CYCLE 50

void temu_iterate(){
	sdl_refresh(vm);
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

	p->display_device = "simplefb";
	p->width = 320;
	p->height = 200;
	sdl_init(p->width, p->height);
	p->console = console_init(TRUE);

	vm = p->vmc->virt_machine_init(p);
}
'''

def gen_api():
	tmp = '/tmp/tinyemu_api.c'
	api = [API_INC, API_CONSOLE, API_VM]
	open(tmp,'wb').write('\n'.join(api).encode('utf-8'))
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
		'-DDUMP_INVALID_MEM_ACCESS',
		'-DDUMP_MMU_EXCEPTIONS',
		'-DDUMP_INTERRUPTS',
		'-DDUMP_INVALID_CSR',
		'-DDUMP_EXCEPTIONS',
		'-DDUMP_CSR',

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
	if not os.path.isfile(LIBTEMU): build()
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
	if '--build' in sys.argv: build()
	test()
