# History

dsari was written to scratch a personal itch:
[I](http://www.finnie.org/) wanted a lightweight CI environment for [Finnix](http://www.finnix.org/) builds, but had grown beyond what simple cron scripts could provide.
I had been using Jenkins, but found the Java and memory requirements to be excessive, especially on armhf builders.
So I went and began writing my own scheduler, but generally didn't want to take myself too seriously.

Preserved below is the original README.md, written before any code had been produced.
Enjoy!

# dsari - Do Something and Record It

## About
dsari is described as a "Jenkins killer", in that I want to kill Jenkins.  It is a small scheduler which does something (something you configure) and records the output (somewhere).

## Development goals
1. Write a small script which does 85% of the features I need, and a random handful of features I don't really need.
2. Deploy it and forget about it for the next year or so.
3. Add a handful of extra features.
4. Realize six other people are also using dsari, two of which have filed a combined 76 bugs and feature requests.
  1. Fix three of the bugs.
  2. Implement two of the feature requests.
  3. Mark the other 71 WONTFIX.
5. Add a bunch more functionality, making the entire project unwieldy and complex.
6. Rename the project after a C&D from a commercial project with a similar name.
7. Rewrite the entire project in Go.
8. Abandon the project.
9. Sourceforge picks up the project files, wraps them in malware and re-releases them.
