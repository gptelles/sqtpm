#include <stdlib.h>
#include <stdio.h>

int main() {

  int i,j;
  FILE* F;

  scanf("%d",&j);

  if ((F = fopen("teste.txt","r"))) {
    for (i=0; i<=j; i++)
      printf("%d\n",i);
  }
  else {
    for (i=0; i<=j, i<=5; i++)
      printf("%d\n",i);
  }

  return 1;
}
