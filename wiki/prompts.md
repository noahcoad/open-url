# useful LLM prompts

plan link-inside-file in @prompts.md

## link-inside-file
we want to be able to link to a specific location within a target file
syntax like:
to line number: file::XXX .. hello.txt::234
to first instance of search text: file::"search text" .. hello.txt::"puppy dog"
to first instance of regex: file::/regex/ .. hello.txt:/^# header/
keep in mind that the file name itself may be encapsuted like "hello world.txt"::XXX
or have slash space like: hello\ world.txt:XXX
and we need a new sublime command called "Copy Path with Location" that copies to the clipboard the file path with one of these target methods, for now let's have it use the regex syntax with the first 5 words of a line, like `file::\^## my header\`
and on "Open URL" it should both open the file and go to the target location
