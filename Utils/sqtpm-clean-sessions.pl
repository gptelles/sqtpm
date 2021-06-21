#!/usr/bin/perl

# Remove expired sqtpm sessions.
# If no session is left it returns 1, otherwise it returns 0.
# G.P. Telles, 2015.

use File::Find;
$/;

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

