#define _GNU_SOURCE
#include <stdio.h>
#include <unistd.h>
#include <stdlib.h>
#include <dirent.h>
#include <sys/stat.h>
#include <string.h>
#include <signal.h>
#include <ctype.h>
#ifndef PATH_MAX
#define PATH_MAX 1024
#endif

int main(int argc, char *argv[])
{
	char *directory;
	DIR *d;
	struct dirent *de;
	char buf[PATH_MAX];
	size_t directory_len;

	if (argc < 2) {
		fprintf(stderr,"%s: <directory>\n", argv[0]);
		exit(1);
	}
	
	directory = argv[1];

	/* make it absolute */
	if (directory[0] != '/') {
		char *cwd = getcwd(buf, sizeof(buf));
		char *dir;
		int len;
		if (cwd == NULL) {
			perror("cwd");
			exit(1);
		}
		/* Add 2 for / + \0 */
		len = strlen(cwd) + strlen(directory) +2;
		dir = (char*)malloc(len * sizeof(char));
		sprintf(dir, "%s/%s", cwd, directory);
		dir[len-1] = '\0';
		directory = dir;
	}

	/* resolve links etc */
	directory = realpath(directory, buf);

	if (directory == NULL) {
		perror("realpath");
		exit(1);
	}

	directory_len = strlen(directory);
	
	d = opendir("/proc");
	if (d == NULL) {
		perror("/proc");
		exit(1);
	}

	while ((de = readdir(d))) {
		const char *name = de->d_name;
		char *cwd_path, *real_cwd;
		char cwd[PATH_MAX], buf2[PATH_MAX];
		ssize_t link_size;
		int len;

		if (!isdigit(name[0])) continue;
		#ifdef __sun
		len = strlen(name) + strlen("/proc//path/cwd") + 1;
		cwd_path = (char*)malloc(len * sizeof(char));
		sprintf(cwd_path, "/proc/%s/path/cwd", name);
		#else
		len = strlen(name) + strlen("/proc//cwd") + 1;
		cwd_path = (char*)malloc(len * sizeof(char));
		sprintf(cwd_path, "/proc/%s/cwd", name);
		#endif
		cwd_path[len - 1] = '\0';
		link_size = readlink(cwd_path, cwd, sizeof(cwd));
		free(cwd_path);
		if (link_size == -1 || link_size >= sizeof(cwd)) {
			continue;
		}

		cwd[link_size] = '\0';
		real_cwd = realpath(cwd, buf2);
		if (real_cwd == NULL) {
			continue;
		}

		if (strncmp(directory, real_cwd, directory_len) == 0 &&
		    (real_cwd[directory_len] == 0 || real_cwd[directory_len] == '/')) {
			/* kill it! */
			printf("Killing process %s\n", name);
			kill(atoi(name), SIGKILL);
		}
		
	}
	
	return 0;
}
