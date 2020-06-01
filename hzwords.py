"""Hanzi Words

Usage:
    hzwords [-jvn] [-i CONFIGFILE] [-o OUTFILE] 
	
Options:
    -i CONFIGFILE    Config file (defaults to hzwords.ini, from HOME, ~, .)
    -o OUTFILE       Ouptut file (default is stdout).
    -j --justwords   Just output words (no other note fields).
    -v --verbose     Verbose output (overrides config).
    -n --nosounds    Don't generate sound files (overrides config).
    -h --help        Show this screen.
"""

import sqlite3
import csv
import pprint
import itertools
import os
import pickle
import string
import sys
import importlib
import configparser

from docopt import docopt
from docopt import DocoptExit

from typing import Dict
from typing import List
from typing import Any


from functools import total_ordering

CONFIG_FILE = 'hzwords.ini'

MAX_WORD_LENGTH = 3
MIN_FREQ_RATIO = 0
MAX_GLOBAL_RANK = 5000
MAX_WORDS_PER_HANZI = 5
IGNORE_TOP_KNOWN_HANZI = 25

# global setting, supposed to remain constant after first assignment
VERBOSE = False

config = configparser.ConfigParser()
configMain = None



StrStr_Dict = Dict[str, str]
StrInt_Dict = Dict[str, int]
Str_StrInt_Dict = Dict[str, StrInt_Dict]
Str_StrStr_Dict = Dict[str, StrStr_Dict]

def saveList(data: List[str], filename: str):
	with open(filename, 'w', encoding='UTF-8') as f:
#		f.writelines([x.encode('UTF-8') + u'\n' for x in data])
		f.writelines([x + '\n' for x in data])

def readList(filename: str) -> List[str]:
	with open(filename, 'r', encoding='UTF-8') as f:
		return f.read().split('\n')

class ankiReviewData:

	def __init__(self, reps = 0, lapses = 0):
		self.reps = reps
		self.lapses = lapses

	def __iadd__(self, other):
		self.reps += other.reps
		self.lapses += other.lapses
		return self

	@property
	def lapseRate(self):
		return self.lapses / max(1, self.reps)

#	def __str__(self):
#		return "{'reps':self.reps, 'lapses':self.lapses, 'lapseRate':self.lapseRate}"

	def __repr__(self):
		x = {'reps':self.reps, 'lapses':self.lapses, 'lapseRate':self.lapseRate}
		return f'{x}'

@total_ordering
class hanziStats(ankiReviewData):
	def __init__(self):
		ankiReviewData.__init__(self)
		self.freq = 0
		self.hasMonoSyllable = False

	def __eq__(self, other):
		return (self.freq == other.freq and self.lapseRate == other.lapseRate)

	def __ne__(self, other):
		return not (self == other)

	def __lt__(self, other):
		return (self.freq < other.freq or self.lapseRate > other.lapseRate)

	def __cmp__(self, other):
		freq_cmp = cmp(self.freq, other.freq)
		x = freq_cmp if freq_cmp != 0 else cmp(other.lapseRate, self.lapseRate)
		return x

#	def __str__(self):
#		return f'{self.freq}' + str(ankiReviewData)

	def __repr__(self):
		x = {'hasMonoSyllable':self.hasMonoSyllable, 'freq':self.freq, 'ankiReviewData':ankiReviewData.__repr__(self)}
		return f'{x}'

KnownWordsDict = Dict[str, ankiReviewData] 
HanziStatsDict = Dict[str, hanziStats]


def isChinese(c) -> bool:
	return c >= u'\u4e00' and c <= u'\u9fff'

def allChinese(s) -> bool:
	for c in s:
		if not isChinese(c): return False
	return True

def sortDictByValues(d: Dict[Any, Any], reverse: bool = False):
	return {k:v for k,v in sorted(d.items(), key=lambda x: x[1], reverse=reverse)}


def checkConfigPath(configSection, configName):

	fileName = configSection[configName]

	if not fileName or len(fileName) == 0:
		raise Exception("%s missing or empty." % configName)
	elif not os.path.exists(fileName):
		raise Exception("%s '%s' does not exist." % (configName, fileName))

	return fileName


def readConfig(configFile, checkHome = True):
	### Checks HOME environment first, then ~, then current directory

	fileToRead = configFile

	if checkHome:
		homeConfigFile1 = os.path.join(os.getenv('HOME'),  configFile);
		homeConfigFile2 = os.path.join(os.path.expanduser('~'),  configFile);

		print(homeConfigFile1)
		print(homeConfigFile2)

		if os.path.exists(homeConfigFile1):
			fileToRead = homeConfigFile1
		elif os.path.exists(homeConfigFile2):
			fileToRead = homeConfigFile2

	config.read(fileToRead)

	VERBOSE = config['Main'].get('Verbose', False)

def getCCCEDICT(cccdb: str, proper: bool = False) -> StrStr_Dict:

	conn = sqlite3.connect(cccdb)
	c = conn.cursor()

	## word/phrase list
	ccc: StrStr_Dict = {}

	r: List[str]
	for r in c.execute('SELECT simplified,english FROM cidian'):
		if (r[1] is None):
			continue

		if (len(r[1]) == 0):
			continue

		x = r[1][0]
		if proper or not x.isupper():
			ccc.update({r[0]:r[1]})

	conn.close()

	return ccc


def readGlobalWordFreq(globWordFreqFile):
	pick = './gwf.pickle'
	if os.path.exists(pick):
		o = open(pick, 'rb')
		wf = pickle.load(o)
		o.close()
		return wf
		
	wf = {}

	o = open(globWordFreqFile, 'r',encoding='utf-8')
	for r in csv.reader(o, delimiter='\t'):
		if allChinese(r[0]):
			n = int(r[1])
			wf.update({r[0]:n})

	o.close()

	o = open(pick, 'wb')
	pickle.dump(wf, o)
	o.close()

	return wf


def reduceGlobWordFreq(globWordFreq: StrInt_Dict, maxLen: int, maxRank: int, minFreqRatio: int) -> StrInt_Dict:

	totFreq: int = sum(globWordFreq.values())

	redWordFreq: StrInt_Dict = {}
	n: int = 0
	for word, freq in itertools.islice(globWordFreq.items(), maxRank):
#		n += 1
#		print(n)
		if len(word) > 1 and len(word) <= maxLen and freq / totFreq > minFreqRatio:
			redWordFreq.update({word:freq})

#	print("len(redWordFreq) = %i" % len(redWordFreq))

	return redWordFreq

def createHanziToWordFreq(globWordFreq) -> Str_StrInt_Dict:
	# create dict of hanzi to compound words + freqs

	hzToWordFreq: Str_StrInt_Dict = {}
	n: int = 0
	for word, freq in globWordFreq.items():
		for hz in word:
			x = hzToWordFreq.get(hz,{})
			x.update({word:freq})
			hzToWordFreq.update({hz:x})

	hz: str
	x: StrInt_Dict
	for hz, x in hzToWordFreq.items():
		hzToWordFreq[hz] = sortDictByValues(x, True)

	return hzToWordFreq



## get character frequency from anki vocabulary list

def getKnownWordsFromAnki(ankidb, deckid):

	conn = sqlite3.connect(ankidb)
	c = conn.cursor()

	d = (deckid,)

	## word/phrase list
	ww = {}

	# q = 'SELECT id,flds,SUM(c.lapses) FROM notes as n, cards as c WHERE n.mid=? and c.nid = n.id'
	# q = 'SELECT id,flds,(SELECT SUM(lapses) FROM cards WHERE nid = notes.id) as lapses FROM notes WHERE mid=?'
	q = 'SELECT n.id, n.flds, c.reps, c.lapses FROM notes AS n, cards AS c WHERE n.mid=? AND c.nid = n.id AND c.ord = 2'
	for r in c.execute(q, d):
		# word/phrase, first field in "flds
	#	print(r)
		w = r[1].split('\x1f')[0].replace('<br>','')

		card = ankiReviewData(
			reps = r[2], 
			lapses = r[3])

		# add to anki vocabulary word list
		ww.update({w:card})

		x = 1

	#	print(w
		
#	ww = sortDictByValues(ww, True)
	conn.close()

	return ww

def isPunctuation(char):
	return char in ['。','？','.','<','>','?',',']

def createKnownHanziStats(knownWords: KnownWordsDict):

	hzStats: HanziStatsDict = {}

	# words in ww
	word: str
	wordRev: ankiReviewData
	for word, wordRev in knownWords.items():

		# don't add to freq if has no reviews
		if wordRev.reps == 0:
			continue

		# h = hanzi character from word/phrase w
		hz: str
		for hz in word:

			if not isChinese(hz) or isPunctuation(hz):
				continue

			hzStat: hanziStats = hzStats.get(hz,hanziStats())

			hzStat.freq += 1

			if len(word) == 1:
				hzStat.hasMonoSyllable = True
				hzStat.reps = wordRev.reps
				hzStat.lapses = wordRev.lapses
			elif not hzStat.hasMonoSyllable:
				hzStat += wordRev

			hzStats.update({hz:hzStat})

			x = 1

	hzStats = sortDictByValues(hzStats)

	return hzStats




def deleteKnownWordsAndUnknownAndTopHanzi(globWordFreq: Str_StrInt_Dict, vocabWords: KnownWordsDict, hzStats: HanziStatsDict, ignoreTopHanzi: int):
	"""Delete known words and unknown and top frequency hanzi from global word list.

	Parameter constraints:
		Anki vocabulary list.
		Vocabulary Hanzi stats.
		Hanzi must not appear in top <ignoreTopHanzi> ranked by frequency in vocabulary.
	"""
	
	## make a copy of the global word frequency for modification
	reducedWordFreq: StrInt_Dict = globWordFreq.copy()

	## top known hanzi to ignore
	topHz: HanziStatsDict = itertools.islice(hzStats.items(), ignoreTopHanzi)

	## loop through all the global words

	word: str
	for word in globWordFreq.keys():
#		print("checking word", w)

		## delete if in known words

		if word in vocabWords:
			reducedWordFreq.pop(word)
		else:
			hz: str
			for hz in word:
				## delete if we don't know the hanzi (not in db or has no reviews), or it's in the top known hanzi list
				if not hz in hzStats or hzStats[hz].freq == 0 or hz in topHz:
					reducedWordFreq.pop(word)
					break

	return reducedWordFreq


def getNewWordsAmongKnownHanzi(hzToWordFreq: Str_StrInt_Dict, knownHzStats: HanziStatsDict, maxWords: int, ccc: StrStr_Dict) -> StrInt_Dict:
	"""Select words from global word frequency list.

	Paramter constraints:
		All Hanzi in word must be known (appears in knownHzStats).
		Hanzi in new words must not cumulatively appear more than <maxWords> times in the new list + the existing vocabulary list.
		Word must appear in <ccc> (CC-CEDICT).

	Other constraints:
		CC-CEDICT defintion cannot be old/archaic usage.
	"""


	newWords: StrInt_Dict = {}
	
	hz:str
	hzStat: hanziStats
	for hz, hzStat in knownHzStats.items():

		numNewWords: int = max(0, maxWords - hzStat.freq)

#		print(h, ": ", n, ", add ", nnw)
		if numNewWords > 0 and hz in hzToWordFreq:
			x: StrInt_Dict = {}
			for word,freq in hzToWordFreq[hz].items():

				## throw away word if not in CC-CEDICT
				if not word in ccc:
					continue

				cccDef = ccc[word]
				if cccDef is None:
					continue

				## throw away if old/archaic word
				archaic: bool = True if cccDef.find('(old)') >= 0 or cccDef.find('archaic ') >= 0 or cccDef.find('(archaic)') >= 0 else False

				if archaic:
					continue

				## only keep word if we currently know all its hanzi
				keep: bool = True
				
				wordHz: str
				for wordHz in word:
					if knownHzStats[wordHz].freq >= maxWords:
						keep = False
						break

				if keep:
					knownHzStats[hz].freq += 1
					x.update({word:freq})
				
	#			print({x})
			newWords.update(x)

	newWords = sortDictByValues(newWords, True)

	return newWords

def getNewWordList():

	configMain = config['Main']
#	print(configMain)

#	print("Known Hanzi Stats")
#	print("-----------")
#	print(knownHzStats)

	globWordFreqFile = checkConfigPath(configMain, 'GlobalWordFreq')
	print("Reading global word freq from %s..." % globWordFreqFile)
	globWordFreq: StrInt_Dict = readGlobalWordFreq(globWordFreqFile)

	
	cccFile = checkConfigPath(configMain, 'CCCEDICT')
	print("Reading CC-CEDICT from %s..." % cccFile)
	ccc: StrStr_Dict = getCCCEDICT(cccFile)


	ankiProfileDir = checkConfigPath(configMain, 'AnkiProfileDir')
	ankiDB = os.path.join(ankiProfileDir, 'collection.anki2')
	vocabDeckId = int(configMain.get('VocabDeckId', None))

	print("Reading Anki vocabulary from %s, deck id %i..." % (ankiDB, vocabDeckId))
	vocabWords: KnownWordsDict = getKnownWordsFromAnki(ankiDB, vocabDeckId)
#	print(len(vocabWords))
#	saveList(vocabWords, 'vocab.txt')
	# pprint.pprint(knownWords)


	print()

	maxLen = int(configMain.get('MaxWordLength', MAX_WORD_LENGTH))
	maxRank = int(configMain.get('MaxGlobalRank', MAX_GLOBAL_RANK))
	minFreqRatio = int(configMain.get('MinFreqRatio', MIN_FREQ_RATIO))

	print("Reducing global word freq to max word length %i, max rank %i, min freq ratio %f..." % (maxLen, maxRank, minFreqRatio))
	redWordFreq: StrInt_Dict = reduceGlobWordFreq(globWordFreq, maxLen, maxRank, minFreqRatio)


	print("Calculating known Hanzi statistics...")
	knownHzStats: HanziStatsDict = createKnownHanziStats(vocabWords)
#	print(len(knownHzStats))

	
	ignoreTopKnownHz = int(configMain.get('IgnoreTopKnownHanzi', IGNORE_TOP_KNOWN_HANZI))
	print("Removing all vocabulary words and top known Hanzi from global word list...")
	unkRedWordFreq: StrInt_Dict = deleteKnownWordsAndUnknownAndTopHanzi(redWordFreq, vocabWords, knownHzStats, ignoreTopKnownHz)
#	print(len(unkRedWordFreq))

	print("Creating Hanzi to word frequency mapping...")
	hzToUnkRedWordFreq: Str_StrInt_Dict = createHanziToWordFreq(unkRedWordFreq)


	maxWordsPerHz = int(configMain.get('MaxWordsPerHanzi', MAX_WORDS_PER_HANZI))
	print("Selecting unknown words with %i maximum words per Hanzi..." % maxWordsPerHz)
	newWords = getNewWordsAmongKnownHanzi(hzToUnkRedWordFreq, knownHzStats, maxWordsPerHz, ccc)

	print()


	print("Number of words in global list:           {:>7,d}".format(len(globWordFreq)))
	print("Number of reduced words in global list    {:>7,d}".format(len(redWordFreq)))
	print("Number of non-proper words in CCCEDICT:   {:>7,d}".format(len(ccc)))
	print("Number of words/phrases in vocab list:    {:>7,d}".format(len(vocabWords)))
	print("Number of Hanzi in known vocab list:      {:>7,d}".format(len(knownHzStats)))
	print("Number of words in reduced global list")
	print("  excluding unknown hanzi and top hanzi:  {:>7,d}".format(len(unkRedWordFreq)))
	print("Number of selected new words:             {:>7,d}".format(len(newWords)))
	print("--------------------------------------------------------")

	#print("New Known Hanzi Freq")
	#print("-----------")
	#pprint.pprint(knownHzStats)

#	pprint.pprint(newWords)

	return newWords

def hotPatch(self):
	filename = '{}_{}_{}.mp3'.format(
		self.sanitize(self.text), self.service, self.lang
	)
	return os.path.join(hotPatch.mediaDir, filename)

hotPatch.mediaDir: str = ''

def hotPatchReduxMediaDir(redux, mediaDir):
	redux.tts.AudioDownloader.get_path = hotPatch
	hotPatch.mediaDir = mediaDir
	importlib.reload(redux.sound)


def nosound(hanzi, source=None):
	return ''

def turnOffReduxSounds(redux):
	redux.sound.sound = nosound
	importlib.reload(redux.behavior)

def fillNoteFields(words: StrInt_Dict, flds: List[str], noSounds=False) -> Str_StrStr_Dict:

	REDUX_ADDON_ID = '1128979221'

	configMain = config['Main']

	ankiDir = checkConfigPath(configMain, 'AnkiDir')
	ankiAddonsDir = checkConfigPath(configMain, 'AnkiAddonsDir')

	sys.path.insert(0, ankiDir)
	sys.path.append(ankiAddonsDir)



#	print(sys.path)


	redux = __import__(REDUX_ADDON_ID)
#	print(redux)

#	for k,v in sys.modules.items():
#		if k.find('sound') >= 0:
#			print(k, ":", v)

#	return

	if noSounds:
		turnOffReduxSounds(redux)
	else:
		hotPatchReduxMediaDir(redux, os.path.join(checkConfigPath(configMain, 'AnkiProfileDir'), 'collection.media'))

	beh = redux.behavior

#	print(beh)
#	print(dir(beh))

	notes: Str_StrStr_Dict = {}

	keyFld = 'Hanzi'

	w: str
	i: int = 0
#	ww = [words[0]]
	nwords = len(words)
	for w in words:
		i += 1
		note = {}

		for f in flds:
			note.update({f:''})

		note[keyFld] = w

		print("%s (%i/%i)" % (w, i, nwords))
		beh.update_fields(note, keyFld, flds)

		for k,v in note.items():
			note[k] = v.replace('\t','').replace('\n','')

		notes.update({w:note})


	return notes

def createNotes(words: StrInt_Dict, notesFile: str, noSounds=False):

	flds = ['Hanzi','Meaning','Reading','Color','Sound','Decomposition','Classifier']

	notes = fillNoteFields(words, flds, noSounds)
	
	f = open(notesFile, 'w', newline='', encoding='UTF-8') if notesFile else sys.stdout

#	csv.register_dialect('tab', delimiter = '\t', quoting = csv.QUOTE_NONE)
	csv.register_dialect('tab', delimiter = '\t')

	w =  csv.DictWriter(f, flds, dialect = 'tab')
#	w.writeheader()
	for note in notes.values():
#		print(note)
		w.writerow(note)

	return

def main():

	args = docopt(__doc__, version='hzwords 0.1.0')

	outFile = args['-o']
	configFile = args['-i'] or CONFIG_FILE

	readConfig(configFile, checkHome = args['-i'] is None)

	VERBOSE = args['--verbose']
	
	newWords = getNewWordList()

	if args['--justwords']:
		for x in newWords:
			print(x)
	else:
		createNotes(newWords, outFile, args['--nosounds'])




if __name__ == '__main__':
	main()

