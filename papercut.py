#!/usr/bin/env python
# Copyright (c) 2001 Joao Prado Maia. See the LICENSE file for more information.
# $Id: papercut.py,v 1.5 2002-01-11 20:29:34 jpm Exp $
import SocketServer
import sys
import signal
import time
import settings

__VERSION__ = '0.3.1'
# set this to 0 (zero) for real world use
__DEBUG__ = 1
__TIMEOUT__ = 60

# some constants to hold the possible responses
ERR_NOTCAPABLE = '500 command not recognized'
ERR_NOPOSTALLOWED = '440 posting not allowed'
ERR_NOPOSTMODE = '201 Hello, you can\'t post'
ERR_CMDSYNTAXERROR = '501 command syntax error (or un-implemented option)'
ERR_NOSUCHGROUP = '411 no such news group'
ERR_NOGROUPSELECTED = '412 no newsgroup has been selected'
ERR_NOARTICLESELECTED = '420 no current article has been selected'
ERR_NOARTICLERETURNED = '420 No article(s) selected'
ERR_NOPREVIOUSARTICLE = '422 no previous article in this group'
ERR_NONEXTARTICLE = '421 no next article in this group'
ERR_NOSUCHARTICLENUM = '423 no such article number in this group'
ERR_NOSLAVESHERE = '202 no slaves here please (this is a read-only server)'
ERR_NOSUCHARTICLE = '430 no such article'
ERR_NOIHAVEHERE = '435 article not wanted - do not send it'
ERR_NOSTREAM = '500 Command not understood'
ERR_TIMEOUT = '503 Timeout after %s seconds, closing connection.'
ERR_NOTPERFORMED = '503 program error, function not performed'
STATUS_HELPMSG = '100 help text follows'
STATUS_GROUPSELECTED = '211 %s %s %s %s group selected'
STATUS_LIST = '215 list of newsgroups follows'
STATUS_STAT = '223 %s <%s@%s> article retrieved - request text separately'
STATUS_ARTICLE = '220 <%s@%s> All of the article follows'
STATUS_NEWGROUPS = '231 list of new newsgroups follows'
STATUS_NEWNEWS = '230 list of new articles by message-id follows'
STATUS_HEAD = '221 %s <%s@%s> article retrieved - head follows'
STATUS_BODY = '222 %s <%s@%s> article retrieved - body follows'
STATUS_READYNOPOST = '201 %s Papercut %s server ready (no posting allowed)'
STATUS_CLOSING = '205 closing connection - goodbye!'
STATUS_XOVER = '224 Overview information follows'
STATUS_XPAT = '221 Header follows'
STATUS_LISTGROUP = '211 list of article numbers follow'
STATUS_XGTITLE = '282 list of groups and descriptions follows'
STATUS_XHDR = '221 Header follows'
STATUS_DATE = '111 %s'
STATUS_OVERVIEWFMT = '215 information follows'
STATUS_EXTENSIONS = '215 Extensions supported by server.'

overview_headers = ('Subject', 'From', 'Date', 'Message-ID', 'References', 'Bytes', 'Lines', 'Xref')

# TODO list:
# ----------
# - MODE STREAM (it means several commands at the same time without waiting for responses)
# - Check more the patterns of searching (wildmat) -> backend.format_wildcards() -> Work in progress
# - Show banner on the footer of the articles about the site
# - Implement some sort of timeout mechanism (According to the new NNTP protocol timeouts should not be explained [i.e. no responses])
# - Implement really dynamic backend storages (it's mysql only right now)
# - Add INSTALL and all of the other crap

class NNTPServer(SocketServer.ThreadingTCPServer):
    allow_reuse_address = 1

class NNTPRequestHandler(SocketServer.StreamRequestHandler):
    commands = ('ARTICLE', 'BODY', 'HEAD',
                'STAT', 'GROUP', 'LIST', 'POST',
                'HELP', 'LAST','NEWGROUPS',
                'NEWNEWS', 'NEXT', 'QUIT',
                'MODE', 'XOVER', 'XPAT',
                'LISTGROUP', 'XGTITLE', 'XHDR',
                'SLAVE', 'DATE', 'IHAVE')
    extensions = ('XOVER', 'XPAT', 'LISTGROUP',
                  'XGTITLE', 'XHDR', 'MODE',
                  'OVER', 'HDR')
    terminated = 0
    selected_article = 'ggg'
    selected_group = 'ggg'
    tokens = []

    def handle(self):
        settings.logEvent('Connection from %s' % (self.client_address[0]))
        self.send_response(STATUS_READYNOPOST % (settings.hostname, __VERSION__))
        while not self.terminated:
            self.inputline = self.rfile.readline()
            line = self.inputline.strip()
            self.tokens = line.split(' ')
            print self.tokens
            # NNTP commands are case-insensitive
            command = self.tokens[0].upper()
            settings.logEvent('Received request: %s' % (line))
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
            self.send_response("%s\r\n%s\r\n." % (STATUS_OVERVIEWFMT, "\r\n".join(["%s:" % k for k in overview_headers])))
            return
        elif (len(self.tokens) == 2) and (self.tokens[1].upper() == 'EXTENSIONS'):
            self.send_response("%s\r\n%s\r\n." % (STATUS_EXTENSIONS, "\r\n".join(["%s" % k for k in self.extensions])))
            return
        elif (len(self.tokens) > 1) and (self.tokens[1].upper() == 'NEWSGROUPS'):
            # same functionality as the XGTITLE command, so let's use that existing code
            self.do_XGTITLE()
            return
        elif len(self.tokens) == 2:
            self.send_response(ERR_NOTPERFORMED)
            return
        result = backend.get_LIST()
        lists = []
        for group_name, table in result:
            total, maximum, minimum = backend.get_group_stats(table)
            lists.append("%s %s %s n" % (group_name, maximum, minimum))
        msg = "%s\r\n%s\r\n." % (STATUS_LIST, "\r\n".join(["%s" % k for k in lists]))
        self.send_response(msg)

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
        head, body = backend.get_ARTICLE(self.selected_group, self.tokens[1])
        response = STATUS_ARTICLE % (self.selected_article, self.selected_group)
        msg = "%s\r\n%s\r\n\r\n%s\r\n." % (response, head, body)
        self.send_response(msg)

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
        if self.selected_article == 'ggg':
            self.send_response(ERR_NOARTICLESELECTED)
            return
        if len(self.tokens) == 2:
            if self.tokens[1].find('@') != -1:
                self.tokens[1] = self.get_number_from_msg_id(self.tokens[1])
            body = backend.get_BODY(self.selected_group, self.tokens[1])
        else:
            body = backend.get_BODY(self.selected_group, self.selected_article)
        msg = "%s\r\n%s\r\n." % (STATUS_BODY % (self.selected_article, self.selected_article, self.selected_group), body)
        self.send_response(msg)

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
            head = backend.get_HEAD(self.selected_group, self.tokens[1])
        else:
            if self.selected_article == 'ggg':
                self.send_response(ERR_NOARTICLESELECTED)
                return
            head = backend.get_HEAD(self.selected_group, self.selected_article)
        msg = "%s\r\n%s\r\n." % (STATUS_HEAD % (self.selected_article, self.selected_article, self.selected_group), head)
        self.send_response(msg)

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
        if (self.tokens[1].upper() != 'SUBJECT') and (self.tokens[1].upper() != 'FROM'):
            self.send_response(ERR_CMDSYNTAXERROR)
            return
        if self.selected_group == 'ggg':
            self.send_response(ERR_NOGROUPSELECTED)
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
        msg = "%s\r\n%s\r\n." % (STATUS_XPAT, overviews)
        self.send_response(msg)

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
        msg = "%s\r\n%s\r\n." % (STATUS_LISTGROUP, numbers)
        self.send_response(msg)

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
        msg = "%s\r\n%s\r\n." % (STATUS_XGTITLE, info)
        self.send_response(msg)

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
            return
        msg = "%s\r\n%s\r\n." % (STATUS_XHDR, info)
        self.send_response(msg)

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
        msg = "%s\r\n\t%s\r\n." % (STATUS_HELPMSG, "\r\n\t".join(self.commands))
        self.send_response(msg)

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
            self.send_response(ERR_NOPOSTMODE)
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
        self.send_response(ERR_NOPOSTALLOWED)

    def get_number_from_msg_id(self, msg_id):
        return msg_id[1:msg_id.find('@')]

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
        if __DEBUG__: print 'Closing the request'
        pass


if __name__ == '__main__':
    # set up signal handler
    def sighandler(signum, frame):
        if __DEBUG__: print "\nClosing the socket..."
        server.socket.close()
        time.sleep(1)
        sys.exit(0)

    from backends.mysql import Papercut_Backend
    backend = Papercut_Backend()

    signal.signal(signal.SIGINT, sighandler)
    if __DEBUG__: print 'Starting the server'
    server = NNTPServer((settings.hostname, 31337), NNTPRequestHandler)
    server.serve_forever()
