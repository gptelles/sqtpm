#!/bin/bash

# Host-side execution dispatcher for Docker.
# This file is part of sqtpm.

sharedd='/fs/sqtpm'
container=d90e61613d76

uid=$1
assign=$2
lang=$3
progname=$4
cputime=$5
virtmem=$6
stkmem=$7

A=("$@") 
L=("${A[@]:7}")
l=${#L[@]}

date=`/bin/date +%d%b%y-%H%M%S`

# Bail out if docker is off:
docker version &>/dev/null
st=$?
if [[ $st -ne 0 ]]; then
  echo "$date $0 'docker version' exited with $st. Docker may be down." &>>sqtpm-etc.log
  exit 129;
fi


# Try to start or unpause the container:
st=$(docker ps -a --format "{{.Status}}" --filter "id=$container")
retry=0

if [[ $st == "" ]]; then
  echo "$date $0 'docker ps' exited with e. container $container may not exist." &>>sqtpm-etc.log
  exit 131
fi

if [[ $st =~ \(Paused\) ]]; then
  docker unpause $container
  retry=1	  
elif [[ $st =~ ^Exited || $st =~ ^Created ]]; then
  docker start $container
  retry=1
fi

if [[ $retry -eq 1 ]]; then
  st=$(docker ps -a --format "{{.Status}}" --filter "id=$container")
  if [[ ! $st =~ ^Up ]]; then
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
# execution in the container, then copy the resulting files to the
# user directory in the assignment:
for inputf in *.in; do

  # Get limits:
  tag=${inputf%\.in}

  thecputime=$cputime
  thevirtmem=$virtmem
  thestkmem=$stkmem
  
  for (( j=0; j<$l; j+=4 )); do
    if [[ $tag == ${L[$j]} ]]; then
      thecputime=${L[$j+1]}
      thevirtmem=${L[$j+2]}
      thestkmem=${L[$j+3]}
    fi
  done
  
  \cp $inputf $tmpd

  if [[ -d extra-files ]]; then
    \cp -r extra-files/* $tmpd
  fi

  chmod -R og+rw $tmpd

  \cp $userd/$progname $tmpd
  chmod -R og+rwx $tmpd/$progname
    
  docker exec -u sqtpm -w /home/sqtpm $container /home/sqtpm/docker-etc.sh $dir $inputf $lang $progname $thecputime $thevirtmem $thestkmem

  \cp $tmpd/$tag.run.{out,err,st} $userd
  \rm -rf $tmpd/*
done

\rm -rf $tmpd
exit 0
