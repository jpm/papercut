#!/usr/bin/env python
# Copyright (c) 2002 Joao Prado Maia. See the LICENSE file for more information.
# $Id: papercut.py,v 1.41 2002-03-25 01:03:24 jpm Exp $
import SocketServer
import sys
import signal
import time
import re
import settings
import traceback
import StringIO

__VERSION__ = '0.7.8'
# set this to 0 (zero) for real world use
__DEBUG__ = 0
__TIMEOUT__ = 60

# some constants to hold the possible responses
ERR_NOTCAPABLE = '500 command not recognized'
ERR_CMDSYNTAXERROR = '501 command syntax error (or un-implemented option)'
ERR_NOSUCHGROUP = '411 no such news group'
ERR_NOGROUPSELECTED = '412 no newsgroup has been selected'
ERR_NOARTICLESELECTED = '420 no current article has been selected'
ERR_NOARTICLERETURNED = '420 No article(s) selected'
ERR_NOPREVIOUSARTICLE = '422 no previous article in this group'
ERR_NONEXTARTICLE = '421 no next article in this group'
ERR_NOSUCHARTICLENUM = '423 no such article in this group'
ERR_NOSLAVESHERE = '202 no slaves here please (this is a standalone server)'
ERR_NOSUCHARTICLE = '430 no such article'
ERR_NOIHAVEHERE = '435 article not wanted - do not send it'
ERR_NOSTREAM = '500 Command not understood'
ERR_TIMEOUT = '503 Timeout after %s seconds, closing connection.'
ERR_NOTPERFORMED = '503 program error, function not performed'
ERR_POSTINGFAILED = '441 Posting failed'
STATUS_POSTMODE = '200 Hello, you can post'
STATUS_NOPOSTMODE = '201 Hello, you can\'t post'
STATUS_HELPMSG = '100 help text follows'
STATUS_GROUPSELECTED = '211 %s %s %s %s group selected'
STATUS_LIST = '215 list of newsgroups follows'
STATUS_STAT = '223 %s <%s@%s> article retrieved - request text separately'
STATUS_ARTICLE = '220 <%s@%s> All of the article follows'
STATUS_NEWGROUPS = '231 list of new newsgroups follows'
STATUS_NEWNEWS = '230 list of new articles by message-id follows'
STATUS_HEAD = '221 %s <%s@%s> article retrieved - head follows'
STATUS_BODY = '222 %s <%s@%s> article retrieved - body follows'
STATUS_READYNOPOST = '200 %s Papercut %s server ready (posting allowed)'
STATUS_CLOSING = '205 closing connection - goodbye!'
STATUS_XOVER = '224 Overview information follows'
STATUS_XPAT = '221 Header follows'
STATUS_LISTGROUP = '211 list of article numbers follow'
STATUS_XGTITLE = '282 list of groups and descriptions follows'
STATUS_LISTNEWSGROUPS = '215 information follows'
STATUS_XHDR = '221 Header follows'
STATUS_DATE = '111 %s'
STATUS_OVERVIEWFMT = '215 information follows'
STATUS_EXTENSIONS = '215 Extensions supported by server.'
STATUS_SENDARTICLE = '340 Send article to be posted'
STATUS_READONLYSERVER = '440 Posting not allowed'
STATUS_POSTSUCCESSFULL = '240 Article received ok'

# the currently supported overview headers
overview_headers = ('Subject', 'From', 'Date', 'Message-ID', 'References', 'Bytes', 'Lines', 'Xref')

# we don't need to create the regular expression objects for every request, 
# so let's create them just once and re-use as needed
newsgroups_regexp = re.compile("^Newsgroups:(.*)", re.M)
contenttype_regexp = re.compile("^Content-Type:(.*);", re.M)

class NNTPServer(SocketServer.ThreadingTCPServer):
    allow_reuse_address = 1

class NNTPRequestHandler(SocketServer.StreamRequestHandler):
    # this is the list of supported commands
    commands = ('ARTICLE', 'BODY', 'HEAD',
                'STAT', 'GROUP', 'LIST', 'POST',
                'HELP', 'LAST','NEWGROUPS',
                'NEWNEWS', 'NEXT', 'QUIT',
                'MODE', 'XOVER', 'XPAT',
                'LISTGROUP', 'XGTITLE', 'XHDR',
                'SLAVE', 'DATE', 'IHAVE',
                'OVER', 'HDR')
    # this is the list of list of extensions supported that are obviously not in the official NNTP document
    extensions = ('XOVER', 'XPAT', 'LISTGROUP',
                  'XGTITLE', 'XHDR', 'MODE',
                  'OVER', 'HDR')
    terminated = 0
    selected_article = 'ggg'
    selected_group = 'ggg'
    tokens = []
    sending_article = 0
    article_lines = []
    broken_oe_checker = 0

    def handle(self):
        settings.logEvent('Connection from %s' % (self.client_address[0]))
        self.send_response(STATUS_READYNOPOST % (settings.nntp_hostname, __VERSION__))
        while not self.terminated:
            if self.sending_article == 0:
                self.article_lines = []
            self.inputline = self.rfile.readline()
            if __DEBUG__:
                print "client>", repr(self.inputline)
            line = self.inputline.strip()
            # somehow outlook express sends a lot of newlines (maybe its just my imagination)
            if (not self.sending_article) and (line == ''):
                self.broken_oe_checker += 1
                if self.broken_oe_checker == 10:
                    self.terminated = 1
                continue
            self.tokens = line.split(' ')
            # NNTP commands are case-insensitive
            command = self.tokens[0].upper()
            settings.logEvent('Received request: %s' % (line))
            if command == 'POST':
                if settings.server_type == 'read-only':
                    settings.logEvent('Error - Read-only server received a post request from \'%s\'' % self.client_address[0])
                    self.send_response(STATUS_READONLYSERVER)
                else:
                    self.sending_article = 1
                    self.send_response(STATUS_SENDARTICLE)
            else:
                if self.sending_article:
                    if self.inputline == '.\r\n':
                        self.sending_article = 0
                        try:
                            self.do_POST()
                        except:
                            # use a temporary file handle object to store the traceback information
                            temp = StringIO.StringIO()
                            traceback.print_exc(file=temp)
                            temp_msg = temp.getvalue()
                            # save on the log file
                            settings.logEvent('Error - Posting failed for user from \'%s\' (exception triggered)' % self.client_address[0])
                            settings.logEvent(temp_msg)
                            if __DEBUG__:
                                print 'Error - Posting failed for user from \'%s\' (exception triggered; details below)' % self.client_address[0]
                                print temp_msg
                            self.send_response(ERR_POSTINGFAILED)
                        continue
                    self.article_lines.append(line)
                else:
                    if command in self.commands:
                        getattr(self, "do_%s" % (command))()
                    else:
                        self.send_response(ERR_NOTCAPABLE)
        settings.logEvent('Connection closed (IP Address: %s)' % (self.client_address[0]))

    def do_NEWGROUPS(self):
        """
        Syntax:
            NEWGROUPS date time [GMT] [<distributions>]
        Responses:
            231 list of new newsgroups follows
        """
        if (len(self.tokens) < 3) or (len(self.tokens) > 5):
            self.send_response(ERR_CMDSYNTAXERROR)
            return
        if (len(self.tokens) > 3) and (self.tokens[3] == 'GMT'):
            ts = self.get_timestamp(self.tokens[1], self.tokens[2], 'yes')
        else:
            ts = self.get_timestamp(self.tokens[1], self.tokens[2], 'no')
        groups = backend.get_NEWGROUPS(ts)
        if groups == None:
            msg = "%s\r\n." % (STATUS_NEWGROUPS)
        else:
            msg = "%s\r\n%s\r\n." % (STATUS_NEWGROUPS, groups)
        self.send_response(msg)

    def do_GROUP(self):
        """
        Syntax:
            GROUP ggg
        Responses:
            211 n f l s group selected
               (n = estimated number of articles in group,
                f = first article number in the group,
                l = last article number in the group,
                s = name of the group.)
            411 no such news group
        """
        # check the syntax of the command
        if len(self.tokens) != 2:
            self.send_response(ERR_CMDSYNTAXERROR)
            return
        # check to see if the group exists
        if not backend.group_exists(self.tokens[1]):
            self.send_response(ERR_NOSUCHGROUP)
            return
        self.selected_group = self.tokens[1]
        total_articles, first_art_num, last_art_num = backend.get_GROUP(self.tokens[1])
        self.send_response(STATUS_GROUPSELECTED % (total_articles, first_art_num, last_art_num, self.tokens[1]))

    def do_NEWNEWS(self):
        """
        Syntax:
            NEWNEWS newsgroups date time [GMT] [<distribution>]
        Responses:
            230 list of new articles by message-id follows
        """
        # check the syntax of the command
        if (len(self.tokens) < 4) or (len(self.tokens) > 6):
            self.send_response(ERR_CMDSYNTAXERROR)
            return
        # check to see if the group exists
        if (self.tokens[1] != '*') and (not backend.group_exists(self.tokens[1])):
            self.send_response(ERR_NOSUCHGROUP)
            return
        if (len(self.tokens) > 4) and (self.tokens[4] == 'GMT'):
            ts = self.get_timestamp(self.tokens[2], self.tokens[3], 'yes')
        else:
            ts = self.get_timestamp(self.tokens[2], self.tokens[3], 'no')
        news = backend.get_NEWNEWS(ts, self.tokens[1])
        if len(news) == 0:
            msg = "%s\r\n." % (STATUS_NEWNEWS)
        else:
            msg = "%s\r\n%s\r\n." % (STATUS_NEWNEWS, news)
        self.send_response(msg)

    def do_LIST(self):
        """
        Syntax:
            LIST (done)
            LIST ACTIVE [wildmat]
            LIST ACTIVE.TIMES
            LIST DISTRIBUTIONS
            LIST DISTRIB.PATS
            LIST NEWSGROUPS [wildmat]
            LIST OVERVIEW.FMT (done)
            LIST SUBSCRIPTIONS
            LIST EXTENSIONS (not documented) (done by comparing the results of other servers)
        Responses:
            215 list of newsgroups follows
            503 program error, function not performed
        """
        if (len(self.tokens) == 2) and (self.tokens[1].upper() == 'OVERVIEW.FMT'):
            self.send_response("%s\r\n%s:\r\n." % (STATUS_OVERVIEWFMT, ":\r\n".join(overview_headers)))
            return
        elif (len(self.tokens) == 2) and (self.tokens[1].upper() == 'EXTENSIONS'):
            self.send_response("%s\r\n%s\r\n." % (STATUS_EXTENSIONS, "\r\n".join(self.extensions)))
            return
        elif (len(self.tokens) > 1) and (self.tokens[1].upper() == 'NEWSGROUPS'):
            self.do_LIST_NEWSGROUPS()
            return
        elif len(self.tokens) == 2:
            self.send_response(ERR_NOTPERFORMED)
            return
        result = backend.get_LIST()
        lists = []
        for group_name, table in result:
            total, maximum, minimum = backend.get_group_stats(table)
            if settings.server_type == 'read-only':
                lists.append("%s %s %s n" % (group_name, maximum, minimum))
            else:
                lists.append("%s %s %s y" % (group_name, maximum, minimum))
        self.send_response("%s\r\n%s\r\n." % (STATUS_LIST, "\r\n".join(lists)))

    def do_STAT(self):
        """
        Syntax:
            STAT nnn|<message-id>
        Responses:
            223 n a article retrieved - request text separately
               (n = article number, a = unique article id)
            412 no newsgroup selected
            420 no current article has been selected
            421 no next article in this group
        """
        # check the syntax of the command
        if len(self.tokens) != 2:
            self.send_response(ERR_CMDSYNTAXERROR)
            return
        if self.selected_group == 'ggg':
            self.send_response(ERR_NOGROUPSELECTED)
            return
        if not backend.get_STAT(self.selected_group, self.tokens[1]):
            self.send_response(ERR_NOSUCHARTICLENUM)
            return
        self.selected_article = self.tokens[1]
        self.send_response(STATUS_STAT % (self.tokens[1], self.tokens[1], self.selected_group))

    def do_ARTICLE(self):
        """
        Syntax:
            ARTICLE nnn|<message-id>
        Responses:
            220 n <a> article retrieved - head and body follow
                (n = article number, <a> = message-id)
            221 n <a> article retrieved - head follows
            222 n <a> article retrieved - body follows
            223 n <a> article retrieved - request text separately
            412 no newsgroup has been selected
            420 no current article has been selected
            423 no such article number in this group
            430 no such article found
        """
        # check the syntax
        if len(self.tokens) != 2:
            self.send_response(ERR_CMDSYNTAXERROR)
            return
        if self.selected_group == 'ggg':
            self.send_response(ERR_NOGROUPSELECTED)
            return
        # get the article number if it is the appropriate option
        if self.tokens[1].find('@') != -1:
            self.tokens[1] = self.get_number_from_msg_id(self.tokens[1])
        result = backend.get_ARTICLE(self.selected_group, self.tokens[1])
        if result == None:
            self.send_response(ERR_NOSUCHARTICLENUM)
        else:
            response = STATUS_ARTICLE % (self.selected_article, self.selected_group)
            self.send_response("%s\r\n%s\r\n\r\n%s\r\n." % (response, result[0], result[1]))

    def do_LAST(self):
        """
        Syntax:
            LAST
        Responses:
            223 n a article retrieved - request text separately
               (n = article number, a = unique article id)
        """
        # check if there is a previous article
        if self.selected_group == 'ggg':
            self.send_response(ERR_NOGROUPSELECTED)
            return
        if self.selected_article == 'ggg':
            self.send_response(ERR_NOARTICLESELECTED)
            return
        article_num = backend.get_LAST(self.selected_group, self.selected_article)
        if article_num == None:
            self.send_response(ERR_NOPREVIOUSARTICLE)
            return
        self.selected_article = article_num
        self.send_response(STATUS_STAT % (article_num, article_num, self.selected_group))

    def do_NEXT(self):
        """
        Syntax:
            NEXT
        Responses:
            223 n a article retrieved - request text separately
               (n = article number, a = unique article id)
            412 no newsgroup selected
            420 no current article has been selected
            421 no next article in this group
        """
        # check if there is a previous article
        if self.selected_group == 'ggg':
            self.send_response(ERR_NOGROUPSELECTED)
            return
        if self.selected_article == 'ggg':
            self.send_response(ERR_NOARTICLESELECTED)
            return
        article_num = backend.get_NEXT(self.selected_group, self.selected_article)
        if article_num == None:
            self.send_response(ERR_NONEXTARTICLE)
            return
        self.selected_article = article_num
        self.send_response(STATUS_STAT % (article_num, article_num, self.selected_group))

    def do_BODY(self):
        """
        Syntax:
            BODY [nnn|<message-id>]
        Responses:
            222 10110 <23445@sdcsvax.ARPA> article retrieved - body follows (body text here)
        """
        if self.selected_group == 'ggg':
            self.send_response(ERR_NOGROUPSELECTED)
            return
        if ((len(self.tokens) == 1) and (self.selected_article == 'ggg')):
            self.send_response(ERR_NOARTICLESELECTED)
            return
        if len(self.tokens) == 2:
            if self.tokens[1].find('@') != -1:
                self.tokens[1] = self.get_number_from_msg_id(self.tokens[1])
            article_number = self.tokens[1]
            body = backend.get_BODY(self.selected_group, self.tokens[1])
        else:
            article_number = self.selected_article
            body = backend.get_BODY(self.selected_group, self.selected_article)
        if body == None:
            self.send_response(ERR_NOSUCHARTICLENUM)
        else:
            self.send_response("%s\r\n%s\r\n." % (STATUS_BODY % (article_number, self.selected_article, self.selected_group), body))

    def do_HEAD(self):
        """
        Syntax:
            HEAD [nnn|<message-id>]
        Responses:
            221 1013 <5734@mcvax.UUCP> Article retrieved; head follows.
        """
        if self.selected_group == 'ggg':
            self.send_response(ERR_NOGROUPSELECTED)
            return
        if len(self.tokens) == 2:
            if self.tokens[1].find('@') != -1:
                self.tokens[1] = self.get_number_from_msg_id(self.tokens[1])
            article_number = self.tokens[1]
            head = backend.get_HEAD(self.selected_group, self.tokens[1])
        else:
            if self.selected_article == 'ggg':
                self.send_response(ERR_NOARTICLESELECTED)
                return
            article_number = self.selected_article
            head = backend.get_HEAD(self.selected_group, self.selected_article)
        if head == None:
            self.send_response(ERR_NOSUCHARTICLENUM)
        else:
            self.send_response("%s\r\n%s\r\n." % (STATUS_HEAD % (article_number, self.selected_article, self.selected_group), head))

    def do_OVER(self):
        self.do_XOVER()

    def do_XOVER(self):
        """
        Syntax:
            XOVER [range]
        Responses:
            224 Overview information follows\r\n
            subject\tauthor\tdate\tmessage-id\treferences\tbyte count\tline count\r\n
            412 No news group current selected
            420 No article(s) selected
        """
        if self.selected_group == 'ggg':
            self.send_response(ERR_NOGROUPSELECTED)
            return
        # check the command style
        if len(self.tokens) == 1:
            # only show the information for the current selected article
            if self.selected_article == 'ggg':
                self.send_response(ERR_NOARTICLESELECTED)
                return
        else:
            ranges = self.tokens[1].split('-')
            if len(ranges) == 2:
                # this is a start-end style of XOVER
                overviews = backend.get_XOVER(self.selected_group, ranges[0], ranges[1])
            else:
                # this is a start-everything style of XOVER
                overviews = backend.get_XOVER(self.selected_group, ranges[0])
        if overviews == None:
            self.send_response(ERR_NOARTICLERETURNED)
            return
        if len(overviews) == 0:
            msg = "%s\r\n." % (STATUS_XOVER)
        else:
            msg = "%s\r\n%s\r\n." % (STATUS_XOVER, overviews)
        self.send_response(msg)

    def do_XPAT(self):
        """
        Syntax:
            XPAT header range|<message-id> pat [pat...]
        Responses:
            221 Header follows
            430 no such article
            502 no permission
        """
        if len(self.tokens) < 4:
            self.send_response(ERR_CMDSYNTAXERROR)
            return
        if self.selected_group == 'ggg':
            self.send_response(ERR_NOGROUPSELECTED)
            return
        if not self.index_in_list(overview_headers, self.tokens[1]):
            self.send_response("%s\r\n." % (STATUS_XPAT))
            return
        if self.tokens[2].find('@') != -1:
            self.tokens[2] = self.get_number_from_msg_id(self.tokens[2])
            self.do_XHDR()
            return
        else:
            ranges = self.tokens[2].split('-')
            if len(ranges) == 2:
                overviews = backend.get_XPAT(self.selected_group, self.tokens[1], self.tokens[3], ranges[0], ranges[1])
            else:
                overviews = backend.get_XPAT(self.selected_group, self.tokens[1], self.tokens[3], ranges[0])
        if overviews == None:
            self.send_response(ERR_NOSUCHARTICLE)
            return
        self.send_response("%s\r\n%s\r\n." % (STATUS_XPAT, overviews))

    def do_LISTGROUP(self):
        """
        Syntax:
            LISTGROUP [ggg]
        Responses:
            211 list of article numbers follow
            412 Not currently in newsgroup
            502 no permission
        """
        if len(self.tokens) > 2:
            self.send_response(ERR_CMDSYNTAXERROR)
            return
        if len(self.tokens) == 2:
            # check if the group exists
            if not backend.group_exists(self.tokens[1]):
                self.send_response("%s\r\n." % (STATUS_LISTGROUP))
                return
            numbers = backend.get_LISTGROUP(self.tokens[1])
        else:
            if self.selected_group == 'ggg':
                self.send_response(ERR_NOGROUPSELECTED)
                return
            numbers = backend.get_LISTGROUP(self.selected_group)
        self.send_response("%s\r\n%s\r\n." % (STATUS_LISTGROUP, numbers))

    def do_XGTITLE(self):
        """
        Syntax:
            XGTITLE [wildmat]
        Responses:
            481 Groups and descriptions unavailable
            282 list of groups and descriptions follows
        """
        if len(self.tokens) > 2:
            self.send_response(ERR_CMDSYNTAXERROR)
            return
        if len(self.tokens) == 2:
            info = backend.get_XGTITLE(self.tokens[1])
        else:
            if self.selected_group == 'ggg':
                self.send_response(ERR_NOGROUPSELECTED)
                return
            info = backend.get_XGTITLE(self.selected_group)
        self.send_response("%s\r\n%s\r\n." % (STATUS_XGTITLE, info))

    def do_LIST_NEWSGROUPS(self):
        """
        Syntax:
            LIST NEWSGROUPS [wildmat]
        Responses:
            503 program error, function not performed
            215 list of groups and descriptions follows
        """
        if len(self.tokens) > 3:
            self.send_response(ERR_CMDSYNTAXERROR)
            return
        if len(self.tokens) == 3:
            info = backend.get_XGTITLE(self.tokens[2])
        else:
            info = backend.get_XGTITLE()
        self.send_response("%s\r\n%s\r\n." % (STATUS_LISTNEWSGROUPS, info))

    def do_HDR(self):
        self.do_XHDR()

    def do_XHDR(self):
        """
        Syntax:
            XHDR header [range|<message-id>]
        Responses:
            221 Header follows
            412 No news group current selected
            420 No current article selected
            430 no such article
        """
        if (len(self.tokens) < 2) or (len(self.tokens) > 3):
            self.send_response(ERR_CMDSYNTAXERROR)
            return
        if self.selected_group == 'ggg':
            self.send_response(ERR_NOGROUPSELECTED)
            return
        if (self.tokens[1].upper() != 'SUBJECT') and (self.tokens[1].upper() != 'FROM'):
            self.send_response(ERR_CMDSYNTAXERROR)
            return
        if len(self.tokens) == 2:
            if self.selected_article == 'ggg':
                self.send_response(ERR_NOARTICLESELECTED)
                return
            info = backend.get_XHDR(self.selected_group, self.tokens[1], 'unique', (self.selected_article))
        else:
            # check the XHDR style now
            if self.tokens[2].find('@') != -1:
                self.tokens[2] = self.get_number_from_msg_id(self.tokens[2])
                info = backend.get_XHDR(self.selected_group, self.tokens[1], 'unique', (self.tokens[2]))
            else:
                ranges = self.tokens[2].split('-')
                if len(ranges) == 2:
                    info = backend.get_XHDR(self.selected_group, self.tokens[1], 'range', (ranges[0], ranges[1]))
                else:
                    info = backend.get_XHDR(self.selected_group, self.tokens[1], 'range', (ranges[0]))
        # check for empty results
        if info == None:
            self.send_response(ERR_NOSUCHARTICLE)
        else:
            self.send_response("%s\r\n%s\r\n." % (STATUS_XHDR, info))

    def do_DATE(self):
        """
        Syntax:
            DATE
        Responses:
            111 YYYYMMDDhhmmss
        """
        self.send_response(STATUS_DATE % (time.strftime('%Y%m%d%H%M%S', time.localtime(time.time()))))

    def do_HELP(self):
        """
        Syntax:
            HELP
        Responses:
            100 help text follows
        """
        self.send_response("%s\r\n\t%s\r\n." % (STATUS_HELPMSG, "\r\n\t".join(self.commands)))

    def do_QUIT(self):
        """
        Syntax:
            QUIT
        Responses:
            205 closing connection - goodbye!
        """
        self.terminated = 1
        self.send_response(STATUS_CLOSING)

    def do_IHAVE(self):
        """
        Syntax:
            IHAVE <message-id>
        Responses:
            235 article transferred ok
            335 send article to be transferred.  End with <CR-LF>.<CR-LF>
            435 article not wanted - do not send it
            436 transfer failed - try again later
            437 article rejected - do not try again
        """
        self.send_response(ERR_NOIHAVEHERE)

    def do_SLAVE(self):
        """
        Syntax:
            SLAVE
        Responses:
            202 slave status noted
        """
        self.send_response(ERR_NOSLAVESHERE)

    def do_MODE(self):
        """
        Syntax:
            MODE READER|STREAM
        Responses:
            200 Hello, you can post
            201 Hello, you can't post
            203 Streaming is OK
            500 Command not understood
        """
        if self.tokens[1].upper() == 'READER':
            if settings.server_type == 'read-only':
                self.send_response(STATUS_NOPOSTMODE)
            else:
                self.send_response(STATUS_POSTMODE)
        elif self.tokens[1].upper() == 'STREAM':
            self.send_response(ERR_NOSTREAM)

    def do_POST(self):
        """
        Syntax:
            POST
        Responses:
            240 article posted ok
            340 send article to be posted. End with <CR-LF>.<CR-LF>
            440 posting not allowed
            441 posting failed
        """
        lines = "\r\n".join(self.article_lines)
        # check the 'Newsgroups' header
        group_name = newsgroups_regexp.search(lines, 1).groups()[0].strip()
        if not backend.group_exists(group_name):
            self.send_response(ERR_POSTINGFAILED)
            return
        result = backend.do_POST(group_name, lines, self.client_address[0])
        if result == None:
            self.send_response(ERR_POSTINGFAILED)
        else:
            self.send_response(STATUS_POSTSUCCESSFULL)

    def get_number_from_msg_id(self, msg_id):
        return msg_id[1:msg_id.find('@')]

    def index_in_list(self, list, index):
        for item in list:
            if item.upper() == index.upper():
                return 1
        return 0

    def get_timestamp(self, date, times, gmt='yes'):
        local_year = str(time.localtime()[0])
        if date[:2] >= local_year[2:4]:
            year = "19%s" % (date[:2])
        else:
            year = "20%s" % (date[:2])
        ts = time.mktime((int(year), int(date[2:4]), int(date[4:6]), int(times[:2]), int(times[2:4]), int(times[4:6]), 0, 0, 0))
        if gmt == 'yes':
            return time.gmtime(ts)
        else:
            return time.localtime(ts)

    def send_response(self, message):
        if __DEBUG__: print "Replying:", message
        self.wfile.write(message + "\r\n")
        self.wfile.flush()

    def finish(self):
        # cleaning up after ourselves
        self.terminated = 0
        self.selected_article = 'ggg'
        self.selected_group = 'ggg'
        self.tokens = []
        self.sending_article = 0
        self.article_lines = []
        self.wfile.flush()
        self.wfile.close()
        self.rfile.close()
        if __DEBUG__: print 'Closing the request'


if __name__ == '__main__':
    # set up signal handler
    def sighandler(signum, frame):
        if __DEBUG__: print "\nClosing the socket..."
        server.socket.close()
        time.sleep(1)
        sys.exit(0)

    # dynamic loading of the appropriate backend module
    temp = __import__('backends.%s' % (settings.backend_type), globals(), locals(), ['Papercut_Backend'])
    backend = temp.Papercut_Backend()

    signal.signal(signal.SIGINT, sighandler)
    print 'Papercut %s - starting up' % __VERSION__
    server = NNTPServer((settings.nntp_hostname, settings.nntp_port), NNTPRequestHandler)
    server.serve_forever()
