from struct import unpack_from, unpack, pack, pack_into
import wave
import soundfile
import io
import zlib


bit8 = 0b00000001
bit16 = 0b00000011
bit24 = 0b00000100
bit32 = 0b00001001
bit64 = 0x00001101
bit128 = 127
bit48 = 118
# LSB = Muliple of 16 if not standalone
# LSB1-LSB2 = Values we skipped in the muliplification if its not standalone.
floattype = 0b00010000
inttype = 0b00100000
uinttype = 0b01000000
float16 = floattype | bit16
float8 = floattype | bit8
float24 = floattype | bit24
float32 = floattype | bit32
float48 = floattype | bit48
float64 = floattype | bit64
float128 = floattype | bit128
int8 = inttype | bit8
int16 = inttype | bit16
int24 = inttype | bit24
int32 = inttype | bit32
int48 = inttype | bit48
int64 = inttype | bit64
int128 = inttype | bit128
uint8 = uinttype | bit8
uint16 = uinttype | bit16
uint24 = uinttype | bit24
uint32 = uinttype | bit32
uint48 = uinttype | bit48
uint64 = uinttype | bit64
uint128 = uinttype | bit128


class NewAdpcmStandard:
	def __init__(self):
		self.file = open("OUT.NAS", "wb+", buffering=64)
		self.file.write(b"\xcd" * 64)
		self.file.seek(0)

	def WriteHeader(self, wav):
		f = wave.open(wav, "rb")
		self.data, self.samplerate = soundfile.read(wav)
		self.file.write(pack("3s", b"NAS"))
		if str(self.data.dtype) == "float32":
			self.file.write(pack("B", float32))
		elif str(self.data.dtype) == "float16":
			self.file.write(pack("B", float16))
		elif str(self.data.dtype) == "int8":
			self.file.write(pack("B", int8))
		elif str(self.data.dtype) == "int16":
			self.file.write(pack("B", int16))
		elif str(self.data.dtype) == "int32":
			self.file.write(pack("B", int32))
		elif str(self.data.dtype) == "uint8":
			self.file.write(pack("B", uint8))
		elif str(self.data.dtype) == "uint16":
			self.file.write(pack("B", uint16))
		elif str(self.data.dtype) == "uint32":
			self.file.write(pack("B", uint32))
		else:
			self.file.write(pack("B", bit8))
		size = len(self.data.shape)
		if size < 2:
			chans = 1
		else:
			chans = self.data.shape[1]
			if chans < 7.1:
				chans &= 7
			else:
				chans = chans & 0x0F | 0x80
		samples = self.data.shape[0]  # store as UINT40
		b0 = (samples >> 0) & 0xFF
		b1 = (samples >> 8) & 0xFF
		b2 = (samples >> 16) & 0xFF
		b3 = (samples >> 24) & 0xFF
		b4 = (samples >> 32) & 0xFF
		self.file.write(pack("I", 64))
		self.file.write(pack("B", chans))
		self.file.write(pack("5B", b0, b1, b2, b3, b4))
		self.file.write(pack("B", 4))  # delta
		self.memalign()

	def memalign(self):
		whatwehavehere = self.file.tell()
		gotheremate = (whatwehavehere + 63) & ~63
		padding = gotheremate - whatwehavehere
		print(f"[NAS] Padding {padding} bytes at offset {whatwehavehere}")
		self.file.write(b"\xcd" * padding)

	def fseek(self, num):
		self.file.seek(64 * num)

	def WriteData(self):
		if str(self.data.dtype) == "float64":
			print("[NAS] Downcasting float64 to float32 to reduce file size.")
			self.data = self.data.astype("float32")

		dtype = str(self.data.dtype)

		if dtype == "float32":
			fmt = "f"
			flag = 1.0
		elif dtype == "int16":
			fmt = "h"
			flag = 32767
		elif dtype == "int32":
			fmt = "i"
			flag = 2147483647
		elif dtype == "int8":
			fmt = "b"
			flag = 127
		elif dtype == "uint8":
			fmt = "B"
			flag = 255
		elif dtype == "uint16":
			fmt = "H"
			flag = 65535
		elif dtype == "uint32":
			fmt = "I"
			flag = 2**32 - 1
		else:
			raise ValueError(f"[NAS] Unsupported dtype: {dtype}")

		# If mono, force into fake multichannel container
		if len(self.data.shape) == 1:
			self.data = self.data.reshape(-1, 1)

		num_channels = self.data.shape[1]
		num_samples = self.data.shape[0]

		self.checksum = []

		audio_buffer = io.BytesIO()
		block_size = 4
		tolerance = 0.1 * flag

		written_blocks = 0
		compressed_blocks = 0
		repeated_blocks = 0
		raw_blocks = 0

		for ch in range(num_channels):
			buffer_offset = 0
			for i in range(0, num_samples - block_size, block_size):
				no1 = self.data[i + 0][ch]
				no2 = self.data[i + 1][ch]
				no3 = self.data[i + 2][ch]
				no4 = self.data[i + 3][ch]

				d1 = no2 - no1
				d2 = no3 - no2
				d3 = no4 - no3

				if all(abs(d) <= tolerance for d in (d1, d2, d3)):
					n2 = no2 - no1
					n3 = no3 - no2
					n4 = no4 - no3
					block = pack(f"{4}{fmt}", no1, n2, n3, n4)
					audio_buffer.write(block)
					thechecksum = (
						(buffer_offset - (4096 if buffer_offset > 4096 else 512))
						| (0 << 8)
						| (4 << 16)
						| (int(((no1 - 32) - (n2 - 24) - (n3 - 16) - (n4 - 8))) << 24)
					)
					self.checksum.append(thechecksum)
					compressed_blocks += 1
					buffer_offset += len(block)

				elif (no1 == no2) and (no2 == no3) and (no3 == no4):
					block = pack(f"{1 + 1}{fmt}", 4, no1)
					audio_buffer.write(block)
					rawsum = (
						(buffer_offset - (4096 if buffer_offset > 4096 else 512))
						| (1 << 8)
						| (4 << 16)
						| (int(no1 - 32) << 24)
					)
					thechecksum = rawsum / (4096 if rawsum > 4096 else 512)
					self.checksum.append(thechecksum)
					repeated_blocks += 1
					buffer_offset += len(block)

				else:
					block = pack(f"{4}{fmt}", no1, no2, no3, no4)
					audio_buffer.write(block)
					fallbacksum = (
						(buffer_offset - (4096 if buffer_offset > 4096 else 512))
						| (2 << 8)
						| (4 << 16)
						| (int(((no1 + no2 + no3 + no4) / 4)) << 24)
					)
					self.checksum.append(fallbacksum)
					raw_blocks += 1
					buffer_offset += len(block)

				written_blocks += 1

		# Write the audio chunk (compressed)
		audio_data = audio_buffer.getvalue()
		compressed_data = zlib.compress(audio_data, level=6)

		self.file.write(pack("4s", b"DATA"))
		self.memalign()
		self.file.write(pack("4sI", b"ZLIB", len(compressed_data)))
		self.file.write(compressed_data)
		self.memalign()

		print(f"[NAS] Blocks written: {written_blocks}")
		print(f"[NAS]  ↳ Compressed:  {compressed_blocks}")
		print(f"[NAS]  ↳ Repeated:   {repeated_blocks}")
		print(f"[NAS]  ↳ Raw:        {raw_blocks}")
		print(f"[NAS] Uncompressed size: {len(audio_data)} bytes")
		print(f"[NAS] Compressed size:   {len(compressed_data)} bytes")


	def WriteChecksum(self, wanted = False):
		if wanted == True:
			self.chksptr = self.file.tell()
			self.file.write(pack("4s", b"CHKS"))
			for i in self.checksum:
				self.file.write(pack("d", i))
			self.memalign()
			chkssize = self.file.tell()
			self.file.seek(self.chksptr + 4)
			self.file.write(pack("I", chkssize))
			print(f"[NAS] File size after data write: {self.file.tell()} bytes")
		else:
			self.chksptr = 0

	def WriteChunkPTRS(self):
		self.file.seek(16)
		self.file.write(pack("2I", 64, self.chksptr))


# if __name__ == "__main__":
	# nas = NewAdpcmStandard()
	# nas.WriteHeader("test.wav")
	# nas.WriteData()
	# nas.WriteChecksum()
	# nas.WriteChunkPTRS()