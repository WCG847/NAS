#include <stdint.h>
#include <stdio.h>

FILE* OpenNAS(const char* NHANDLE) {
	FILE* NAS = fopen(NHANDLE, "rb");
	// allocate 64 bytes on the buffer
	char buffer[64];
	fread(buffer, 1, sizeof(buffer), NAS);
}