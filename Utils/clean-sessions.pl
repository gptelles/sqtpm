#!/usr/bin/perl

# Remove expired sqtpm session files.
# If no expired session file is left it returns 0, otherwise it returns 1.
# G.P. Telles, 2015, 2023.

use File::Find;
$/ = "\n";

use constant SESSION_DIR => '/tmp/';

$left = 0;
find(\&wanted,SESSION_DIR);
exit($left ? 1 : 0);



sub wanted {
  !/^sqtpm-.*/ && return;

  open(my $fh,'<',SESSION_DIR . $_) or die("Unable to open $_ : $!");
  my $data = <$fh>;    
  close($fh);
  
  my $D;
  eval($data);

  if (time() >= $D->{_SESSION_ETIME} + $D->{_SESSION_ATIME}) {
    unlink(SESSION_DIR . $_) or print "Unable to delete $_ : $!\n";
    $left++;
  }
}

