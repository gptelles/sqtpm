#include <iostream>
#include "class.h"

using namespace std;

int main() {

  int i,j;

  dummy* D = new dummy();

  cin >> j;

  if (j == 10) {
    D->conta(j);
  }
  else {
    D->conta(j+1);
  }

  return 1;
}
