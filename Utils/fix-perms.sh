#!/bin/bash

if [ "$1" ]; then
  if [ -d $1 ]; then 
    chgrp -R www-data $1
    chmod 2770 $1
    cd $1
    find . -type f -exec chmod 660 {} \;
    chmod 2770 include 2>/dev/null
    chmod 2770 extra-files 2>/dev/null
  else
    echo "$1 is not a directory"
  fi
else
  chmod -R a-s *
  chgrp -R www-data *
  find . -type d -exec chmod 2770 {} \;
  find . -type f -exec chmod 660 {} \;
  chmod 750 *.cgi *.sh
  chmod 640 sqtpm.pm sqtpm.cfg sqtpm.js sqtpm.css moss-sqtpm *.html *.png
  chmod g-s google-code-prettify
  chmod 750 google-code-prettify
  chmod 640 google-code-prettify/*
fi
