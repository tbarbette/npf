#!/bin/bash
url=$1
name=$2
branch=$3

if [ -z "$branch" ] ; then
	branch="master"
fi

if [ -z "$name" ] ; then
	echo "Usage : $0 URL NAME [BRANCH]"
	exit 1
fi

clickfolder=$name/build
if [ ! -e $clickfolder ] ; then
	git clone $url $clickfolder
	cd $clickfolder
	git checkout -q origin/$branch
else
	cd $clickfolder
	git fetch --all
	git checkout -q origin/$branch
fi
uuid=$(git rev-parse HEAD)
if [ -e "../.lastuuid" ] ; then
	prevuuid=$(cat ../.lastuuid)
else
	prevuuid=""
fi
echo $uuid > ../.lastuuid

./configure --enable-dpdk --disable-linuxmodule --enable-user-multithread CFLAGS="-O3" CXXFLAGS="-std=gnu++11 -O3" --enable-bound-port-transfer
make -j 12
cd ../..

for test in ./tests/* ; do
	echo "Running $(basename $test)"
	python perf.py $test $name $uuid $prevuuid | tee $name/$(basename $test).log
	if [ ! $? -eq 0 ] ; then
		echo "Error executing last test... Continuing anyway."
	fi
done

