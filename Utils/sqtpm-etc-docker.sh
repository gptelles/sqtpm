#!/bin/bash

# Host-side execution dispatcher for Docker.
# This file is part of sqtpm.

sharedd='/data/p2'
container=4e80cc12232c

uid=$1
assign=$2
lang=$3
progname=$4
cputime=$5
virtmem=$6
stkmem=$7

date=`/bin/date +%d%b%y-%H%M%S`

# Bail out if docker is off:
docker version &>/dev/null
st=$?
if [[ $st -ne 0 ]]; then
  echo "$date sqtpm-etc-docker.sh 'docker version' exited with $st." &>>sqtpm-etc.log
  exit 129;
fi


# Try to start or unpause the container:
st=$(docker ps -a --format "{{.Status}}" --filter "id=$container")
retry=0

if [[ $st =~ \(Paused\) ]]; then
  docker unpause $container
  retry=1	  
elif [[ $st =~ ^Exited || $st =~ ^Created ]]; then
  docker start $container
  retry=1
fi

if [[ $retry -eq 1 ]]; then
  st=$(docker ps -a --format "{{.Status}}" --filter "id=$container")
  if [[ $st =~ \(Paused\) ]]; then
    echo "$date $0 $container state is paused." &>>sqtpm-etc.log
    exit 131
  elif [[ ! $st =~ ^Up ]]; then
    echo "$date $0 $container state is not up." &>>sqtpm-etc.log
    exit 133
  fi
fi


# Create the temp dir:
umask 0000
dir="$date-$$"
tmpd="$sharedd/$dir"
userd="_${uid}_tmp_"

mkdir $tmpd
if [[ $? -ne 0 ]]; then
  echo "$date $0 mkdir $tmpd failed." &>>sqtpm-etc.log
  exit 135
fi

cd $assign &>/dev/null

# Copy each input file, the extra files and the elf to tmpd, invoke
# execution in the container, then move the resulting files to the
# user directory in the assignment:
for inputf in *.in; do
  \cp $inputf $tmpd

  if [[ -d extra-files ]]; then
    \cp -r extra-files/* $tmpd
  fi

  chmod -R go+rw $tmpd

  \cp $userd/$progname $tmpd
  chmod -R go+rwx $tmpd/$progname
    
  docker exec -u sqtpm -w /home/sqtpm $container /home/sqtpm/docker-etc.sh $dir $inputf $lang $progname $cputime $virtmem $stkmem

  tag=${inputf/.in/}
  \mv $tmpd/$tag.run.{out,err,st} $userd

  \rm -rf $tmpd/*
done

\rm -rf $tmpd
exit 0
