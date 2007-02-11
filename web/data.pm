#!/usr/bin/perl -w
# Simple database query script for the buildfarm
#
# Copyright (C) Andrew Tridgell <tridge@samba.org>     2001-2005
# Copyright (C) Andrew Bartlett <abartlet@samba.org>   2001
# Copyright (C) Vance Lankhaar  <vance@samba.org>      2002-2005
# Copyright (C) Martin Pool <mbp@samba.org>            2001
# Copyright (C) Jelmer Vernooij <jelmer@samba.org>	   2007
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation; either version 2 of the License, or
#   (at your option) any later version.
#   
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#   
#   You should have received a copy of the GNU General Public License
#   along with this program; if not, write to the Free Software
#   Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.

package data;

use util;
use POSIX;
use File::stat;
use FindBin qw($RealBin);

@ISA = qw(Exporter);
use Exporter;
@EXPORT_OK = qw(@hosts %hosts @compilers @pseudo_trees %trees $OLDAGE $DEADAGE);

use strict;
use warnings;

my $WEBDIR = "$RealBin";

my $OLDAGE = 60*60*4;
my $DEADAGE = 60*60*24*4;

##############################################
# this defines what it is possible to build 
# and what boxes. Should be in a config file
my @compilers = util::load_list("$WEBDIR/compilers.list");
my (%hosts) = util::load_hash("$WEBDIR/hosts.list");
my @hosts = sort { $hosts{$a} cmp $hosts{$b} } keys %hosts;
my (%trees) = util::load_hash("$WEBDIR/trees.list");
# these aren't really trees... they're just things we want in the menu.
# (for recent checkins)
my @pseudo_trees = util::load_list("$WEBDIR/pseudo.list");

1;
