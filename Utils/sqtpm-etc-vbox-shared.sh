#!/bin/bash

# Host-side test-cases execution dispatcher for VirtualBox with shared directory.
# This file is part of sqtpm.

sharedd='/mnt/aux'

uid=$1
assign=$2
cputime=$3
virtmem=$4
stkmem=$5

# If the vm is paused, tries to resume it:
st=`vboxmanage showvminfo sqtpm | grep "^State" | sed -e "s/  */ /g" | cut -f 2 -d ' '`
if [[ "$st"  == "paused" ]]; then 
  vboxmanage controlvm sqtpm resume
  sleep 3
  st=`vboxmanage showvminfo sqtpm | grep "^State" | sed -e "s/  */ /g" | cut -f 2 -d ' '`
  if [[ "$st" == "paused" ]]; then 
    exit 1
  fi
fi

# Creates a temp dir:
date=`/bin/date +%d%b%y-%H%M%S`
dir="$date-$$"
tmpd="$sharedd/$dir"
userd="_${uid}_tmp_"

mkdir $tmpd

cd $assign &>/dev/null

for inputf in *.in; do
  # Copies each input file, the elf and extra files to tmpd, invokes
  # execution in the VM, and then moves resulting files to the user
  # directory in the assignment:

  \cp $inputf $tmpd
  \cp $userd/elf $tmpd
  if [[ -d extra-files ]]; then
    \cp -r extra-files/* $tmpd
  fi

  vboxmanage guestcontrol sqtpm execute --image /home/sqtpm/vbox-etc-shared.sh --username sqtpm --password senha --wait-exit --wait-stdout --wait-stderr -- $dir $inputf $cputime $virtmem $stkmem

  tag=${inputf/.in/}
  \mv $tmpd/$tag.run.{out,err,st} $userd

  \rm -rf $tmpd/*
done

\rm -rf $tmpd

