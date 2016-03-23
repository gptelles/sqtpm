CC=/usr/bin/g++
SRC=$(wildcard *.cpp)
elf: $(SRC:%.cpp=%.o)
	$(CC) -Wall -O3 -o $@ $^
clean:
	/bin/rm -r *.o
