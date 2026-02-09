#!/usr/bin/env python3
"""Summarizer module - creates original Romanian summaries using sumy"""
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer
from sumy.nlp.stemmers import Stemmer
from sumy.utils import get_stop_words
import re

def summarize(text, sentences_count=3, language="romanian"):
    if not text or len(text) < 100:
        return text
    try:
        parser = PlaintextParser.from_string(text, Tokenizer(language))
        stemmer = Stemmer(language)
        summarizer = LsaSummarizer(stemmer)
        summarizer.stop_words = get_stop_words(language)
        summary = summarizer(parser.document, sentences_count)
        result = " ".join(str(s) for s in summary)
        return result if result else text[:300]
    except:
        return text[:300]

def summarize_for_article(text, source_name=""):
    s = summarize(text, 3)
    if source_name:
        s += f" (Conform {source_name})"
    return s