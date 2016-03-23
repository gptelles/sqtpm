
$inf = shift;
$outf = shift;

open(IN,"<$inf") || exit(3);
$_ = <IN>;
chomp;
$n = $_;
close(IN);

open(OUT,"<$outf") || exit(3);

$i = 0;
while (<OUT>) {
  chomp;
  if ($i ne $_) {
    close(OUT);
    exit(1);
  }
  $i++;
}

close(OUT);

($i != $n+1) && exit(1);

exit(0);
