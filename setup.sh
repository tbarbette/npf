#!/bin/sh
if [ -e /usr/bin/yum ] ; then
	i="yum -y install"
else
	i="apt-get install -f"
fi

echo "Installing python 3 and libssl"
$i python3 python3-pip libssl-dev

if [ -e /usr/bin/pip3 ] ; then
	p=pip3
else
	p=python3-pip
fi

$p install numpy
$p install -r requirements.txt
