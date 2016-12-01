#!/bin/bash

if [ $1 = "--no-build" ] ; then
	build=False
	shift
else
	build=True
fi
url=$1
name=$2
branch=$3
uuid=$4

if [ -z "$branch" ] ; then
	branch="master"
fi

if [ -z "$name" ] ; then
	echo "Usage : $0 URL NAME [BRANCH [UUID]]"
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

if [ -z "$uuid" ] ; then
	uuid=$(git rev-parse --short HEAD)
fi

if [ -e "../.lastuuid" ] ; then
	prevuuid=$(cat ../.lastuuid)
else
	prevuuid=""
fi
echo $uuid > ../.lastuuid

if [ $build = True ] ; then
	./configure --enable-dpdk --disable-linuxmodule --enable-user-multithread CFLAGS="-O3" CXXFLAGS="-std=gnu++11 -O3" --enable-bound-port-transfer
	make -j 12
fi

cd ../..
exitcode=0
for test in ./tests/* ; do
	echo "Running $(basename $test) for $uuid, compare against $prevuuid"
	python regression.py $test $name $uuid $prevuuid
	if [ ! $? -eq 0 ] ; then
		echo "Error executing last test... Continuing anyway."
		exitcode=1
	fi
done

exit $exitcode
