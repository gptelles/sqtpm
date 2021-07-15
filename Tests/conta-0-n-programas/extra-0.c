#include <stdio.h>

int main() {

  int i,j;

  scanf("%d",&j);

  FILE* f = fopen("extra.txt","r");
  if (!f)
    printf("Nao abriu");

  char str[31];
  fscanf(f,"%s",str);

  printf("%s\n",str);
  return 1;
}
