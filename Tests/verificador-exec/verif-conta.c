
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char** argv) {

  FILE *fin, *fout;
  int n,i,j,fail;

  fin = fopen(argv[1], "r");
  fout = fopen(argv[2], "r");

  fscanf(fin,"%d",&n);


  fail = 0;
  for (i=0; i<=n; i++) {
    
    if (fscanf(fout,"%d ",&j) == 0)
      fail = 1;
    else {
      if (i != j)
	fail = 1;
    }
  }

  if (!feof(fout)) 
     fail = 1;

  return fail;
}
