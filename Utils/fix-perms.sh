#!/bin/bash

if [ "$1" ]; then
  chgrp -R www-data $1
  chmod 2770 $1
  cd $1
  find . -type f -exec chmod 660 {} \;
else
  chgrp -R www-data *
  find . -type d -exec chmod 2770 {} \;
  find . -type f -exec chmod 660 {} \;
  find . -type l -exec chmod 777 {} \;
  chmod 750 *.cgi *.sh
  chmod 640 sqtpm.pm sqtpm.cfg sqtpm.js sqtpm.css *.html *.png
  chmod 660 sqtpm.log *.pass
  chmod -R 650 google-code-prettify
fi
