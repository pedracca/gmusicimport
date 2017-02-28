#!/usr/bin/env python

# Copyright (C) 2013 Guillaume Seguin <guillaume@segu.in>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

import getpass
import argparse
import json
import time
import unicodedata
import re
from gmusicapi import Mobileclient


stripWords = ['a', 'the', 'in', 'of', 'to', 'at', 'from']
normalize_pattern = re.compile(r'\s|\W|\b(' + r'|'.join(stripWords) + r')\b\s*')
parenthesis_pattern = re.compile(r'\(.+?\)')


def normalize_string(str):
    normalized = normalize_pattern.sub('', str.lower())
    normalized = ''.join(c for c in unicodedata.normalize('NFD', normalized) if unicodedata.category(c) != 'Mn')
    return normalized


PERFECT_MATCH = 4
BAD_MATCH = 2
MAX_SECONDS_LENGTH_DIFF = 7


def find_best_match(track, results):
    best = None
    hit_index = 0
    max_score = 0
    for hit_i, hit in enumerate(results):
        potential = hit["track"]
        score = 0
        #print("-> evaluating %d: [%s by %s in %s]" % (hit_i, potential["title"], potential["artist"], potential["album"]))
        if normalize_string(track["title"]) == normalize_string(potential["title"]):
            score += 1
        if normalize_string(track["artist"]) == normalize_string(potential["artist"]):
            score += 1
        if normalize_string(track["album"]) == normalize_string(potential["album"]):
            score += 1
        if abs(int(track["length"]) - (int(potential["durationMillis"]) / 1000)) <= MAX_SECONDS_LENGTH_DIFF:
            score += 1
        if score == PERFECT_MATCH or (score > BAD_MATCH and score > max_score):
            best = potential
            hit_index = hit_i
            max_score = score
            if score == PERFECT_MATCH:
                break
    if not best and results:
        best = results[0]["track"]
    if args.verbose and best:
        quality = "* perfect *"
        if max_score < PERFECT_MATCH and max_score > BAD_MATCH:
            quality = "     - OK -"
        elif max_score <= BAD_MATCH and best:
            quality = "        Bad"
        print("  %s match for [%s by %s in %s] at hit num. %d/%d: [%s by %s in %s]" %
              (quality, track["title"], track["artist"], track["album"],
               hit_index + 1, len(results), best["title"], best["artist"], best["album"]))
    return best


def search_tracks(query):
    results = client.search(query)
    if not results["song_hits"] and parenthesis_pattern.search(query):
        time.sleep(.1)
        results = client.search(parenthesis_pattern.sub('', query))
    return results


if __name__ == "__main__":
    client = Mobileclient()
    parser = argparse.ArgumentParser(description = 'Play Music import script')
    parser.add_argument('-u', '--user', '--username', dest = "username",
                        required = True, help = "Your username")
    parser.add_argument('-v', dest = "verbose", action = "store_true",
                        help = "Increase verbosity")
    parser.add_argument('--dry-run', dest = "dryrun", action = "store_true",
                        help = "Only perform a dry run, "
                               "don't build any playlist")
    parser.add_argument('source', metavar = "playlists.json",
                        help = "JSON file holding playlists")
    args = parser.parse_args()
    print("Logging in as \"%s\" to Google Play Music" % args.username)
    pw = getpass.getpass()
    if not client.login(args.username, pw, Mobileclient.FROM_MAC_ADDRESS):
        print("Authentication failed. Please check the provided credentials.")
    with open(args.source) as f:
        data = json.load(f)
    if args.dryrun:
        print("[/!\] We're currently running in dry-run mode")
    unmatched = {"playlists": []}
    for playlist in data["playlists"]:
        if args.dryrun:
            print("Checking importability of %s" % playlist["title"])
        else:
            print("Importing %s" % playlist["title"])
        unmatched_songs = []
        toimport = []
        for track in playlist["tracks"]:
            query = "%s %s" % (track["title"], track["artist"])
            results = search_tracks(query)
            match = None
            if results["song_hits"]:
                match = find_best_match(track, results["song_hits"])
            if match is not None:
                toimport.append(match["storeId"])
            else:
                print("[!!!] No good match for %s in playlist %s" % (query, playlist["title"]))
                unmatched_songs.append(track)
            time.sleep(.1)
        if unmatched_songs:
            unmatched["playlists"].append({"title": playlist["title"], "tracks": unmatched_songs})
        if not args.dryrun and toimport:
                playlist_id = client.create_playlist(playlist["title"])
                client.add_songs_to_playlist(playlist_id, toimport)
        if not args.dryrun and unmatched["playlists"]:
            with open("unmatched.json", "w") as f:
                json.dump(unmatched, f, indent=2)