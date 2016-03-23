CC=/usr/bin/gcc
SRC=$(wildcard *.c)
elf: $(SRC:%.c=%.o)
	$(CC) -Wall -O3 -o $@ $^
clean:
	/bin/rm -r *.o
