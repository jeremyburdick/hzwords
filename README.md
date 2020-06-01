# **Hanzi Words**

### Hanzi Words is a simple command-line application to create new Anki flashcards for multi-syllabic Chinese words using only Hanzi characters you already know.

#### It lets you expand your vocabulary without having to learn additional characters, and helps to reinforce characters you've already learned.

You can also restrict new words via
1) Rankings and/or occurrence ratios from a word frequency list.
2) Often forgotten characters in your existing Anki vocabulary.
3) Evenly distributing words in your database so characters occur with similar frequency.
4) Ignoring the most common characters (such as 大， 人， 小， etc).
5) Eliminating proper nouns and archaic usages.

The initial version (0.1.0) exports the new cards to a tab-delimited notes textfile, which you can import through the Anki interface to generate the cards directly in your Anki database. 

Future versions may be fully integrated into Anki for ease of use (although this would require some GUI development).

You will need to edit **hzwords.ini** and set the location of a few important files, which are described within.

Also, there are a handful of Python library and support datasets / auxiliary programs required:

**Python Libraries**
* anki
* aqt
* PyQt5
* PyQtWebEngine
* docopt


**Chinese Support Redux Anki Addon** 

This awesome addon is used to fill definitions, pinyin, tone coloring, classifiers, ruby hints, and sounds.

You must install this first from within Anki. The documentation is available here: https://ankiweb.net/shared/info/1128979221


**Chinese Word Frequency List**

The format should be UTF-8 tab-delimited. First column is a Chinese word in Hanzi. Second column is frequency count.

One option based on a 15-billion character corpus is available at https://www.plecoforums.com/download/global_wordfreq-release_utf-8-txt.2593/


**CC-CEDICT: Open Source Chinese-English Dictionary**

This comes bundled with Chinese Support Redux, so you don't need to worry about it.

If you want to explore the data further, you can grab a plain-text copy from https://www.mdbg.net/chinese/dictionary?page=cc-cedict
