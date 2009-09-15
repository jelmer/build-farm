###################################################
# utility functions to support the build farm
# Copyright (C) tridge@samba.org, 2001
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

package util;

use Data::Dumper;

##############################################
# load a list from a file, using : to separate
sub load_list($)
{
	my $fname = shift;
	my @lines;
	open(FH,"<",$fname);
	while (<FH>) {
		chomp;
		push (@lines,$_) unless (/^#/);
	}
	close FH;
	return @lines;
}

##############################################
# load a hash from a file, using : to separate
sub load_hash($)
{
	my $fname = shift;
	my @lines = load_list($fname);
	my %ret;
	for my $l (@lines) {
		if ($l =~ /^([\w\-]*)\s*:\s*(.*)$/) {
			$ret{$1} = $2;
		}
	}
	return %ret;
}

#####################################################################
# check if a string is in an array
sub InArray($$)
{
    my ($s, $a) = @_;
    for my $v (@{$a}) {
		return 1 if ($v eq $s);
    }
    return 0;
}

#####################################################################
# flatten an array of arrays into a single array
sub FlattenArray($) 
{ 
    my $a = shift;
    my @b;
    for my $d (@{$a}) {
		push(@b, $_) foreach (@{$d});
    }
    return \@b;
}

#####################################################################
# flatten an array of hashes into a single hash
sub FlattenHash($) 
{ 
    my $a = shift;
    my %b;
    for my $d (@{$a}) {
		for my $k (keys %{$d}) {
			$b{$k} = $d->{$k};
		}
    }
    return \%b;
}

#####################################################################
# return the modification time of a file
sub FileModtime($)
{
    my($filename) = shift;
    return (stat($filename))[9];
}

#####################################################################
# read a file into a string
sub FileLoad($)
{
    my($filename) = shift;
    local(*INPUTFILE);
    open(INPUTFILE, $filename) || return "";
    my($saved_delim) = $/;
    undef $/;
    my($data) = <INPUTFILE>;
    close(INPUTFILE);
    $/ = $saved_delim;
    return $data;
}

#####################################################################
# write a string into a file
sub FileSave($$)
{
    my($filename) = shift;
    my($v) = shift;
    local(*FILE);
    open(FILE, ">$filename") || die "can't open $filename";    
    print FILE $v;
    close(FILE);
}

#####################################################################
# return a filename with a changed extension
sub ChangeExtension($$)
{
    my($fname,$ext) = @_;
	return "$1.$ext" if ($fname =~ /^(.*)\.(.*?)$/);
    return "$fname.$ext";
}

#####################################################################
# save a data structure into a file
sub SaveStructure($$)
{
    my($filename) = shift;
    my($v) = shift;
    FileSave($filename, Dumper($v));
}

#####################################################################
# load a data structure from a file (as saved with SaveStructure)
sub LoadStructure($)
{
    return eval FileLoad(shift);
}

##########################################
# count the number of lines in a buffer
sub count_lines($)
{
    my $s = shift;
    my $count;
    $count++ while $s =~ /$/gm;
    return $count;
}

################
# display a time as days, hours, minutes
sub dhm_time($)
{
	my $sec = shift;
	my $days = int($sec / (60*60*24));
	my $hour = int($sec / (60*60)) % 24;
	my $min = int($sec / 60) % 60;

	my $ret = "";

	if ($sec < 0) { 
		return "-";
	}

	if ($days != 0) { 
		return sprintf("%dd %dh %dm", $days, $hour, $min);
	}
	if ($hour != 0) {
		return sprintf("%dh %dm", $hour, $min);
	}
	if ($min != 0) {
		return sprintf("%dm", $min);
	}
	return sprintf("%ds", $sec);
}

##############################################
# simple html markup stripper
sub strip_html($) {
	my $string = shift;

	# get rid of comments
	$string =~ s/<!\-\-(.*?)\-\->/$2/g;

	# and remove tags.
	while ($string =~ s&<(\w+).*?>(.*?)</\1>&$2&) {
		;
	}

	return $string;
}

1;
