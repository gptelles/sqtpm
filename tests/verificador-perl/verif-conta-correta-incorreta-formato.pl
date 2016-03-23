
$case = shift;

if ($case =~ /01.in/) {
  exit(0);
}
elsif ($case =~ /02.in/) {
  exit(1);
}
elsif ($case =~ /03.in/) {
  exit(2);
}

