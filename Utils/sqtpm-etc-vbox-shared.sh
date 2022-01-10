#!/bin/bash

# Host-side execution dispatcher for VirtualBox with a shared directory.
# This file is part of sqtpm.

sharedd='/mnt/aux'

uid=$1
assign=$2
lang=$3
progname=$4
cputime=$5
virtmem=$6
stkmem=$7

date=`/bin/date +%d%b%y-%H%M%S`

# Bail out if sqtpm VM is not registered or off:
st=`/usr/bin/vboxmanage showvminfo sqtpm 2>/dev/null` 
if [[ $? -ne 0 ]]; then
  echo "$date sqtpm-etc-vbox-shared.sh unable to get info on VM sqtpm." 2>&1 >>sqtpm-etc.log
  exit 129;
fi

st=`echo "$st" | grep "^State" | sed -e "s/  */ /g" | cut -f 2 -d ' '`
if [[ "$st"  == "powered" ]]; then 
  exit 131;
fi

# If sqtpm VM is paused, try to resume it:
if [[ "$st"  == "paused" ]]; then 
  vboxmanage controlvm sqtpm resume
  sleep 3
  st=`vboxmanage showvminfo sqtpm | grep "^State" | sed -e "s/  */ /g" | cut -f 2 -d ' '`
  if [[ "$st" == "paused" ]]; then 
    exit 133
  fi
fi

# Create a temp dir:
dir="$date-$$"
tmpd="$sharedd/$dir"
userd="_${uid}_tmp_"

mkdir $tmpd
if [[ $? -ne 0 ]]; then
  echo "mkdir $tmpd failed."
  exit 129
fi

cd $assign &>/dev/null

for inputf in *.in; do
  # Copy each input file, the elf and extra files to tmpd, invoke
  # execution in the VM, and then move the resulting files to the user
  # directory in the assignment:

  \cp $inputf $tmpd
  \cp $userd/$progname $tmpd
  
  if [[ -d extra-files ]]; then
    \cp -r extra-files/* $tmpd
  fi

  vboxmanage guestcontrol sqtpm --username sqtpm --password senha run --exe /home/sqtpm/vbox-etc-shared.sh --wait-stdout --wait-stderr -- vbox-etc-shared.sh $dir $inputf $lang $progname $cputime $virtmem $stkmem

  tag=${inputf/.in/}
  \mv $tmpd/$tag.run.{out,err,st} $userd

  \rm -rf $tmpd/*
done

\rm -rf $tmpd

