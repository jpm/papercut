#!/usr/bin/env python
# Copyright (c) 2001 Joao Prado Maia. See the LICENSE file for more information.
# $Id: papercut.py,v 1.2 2002-01-10 21:14:35 jpm Exp $
import SocketServer
import sys
import signal
import time
import settings

__VERSION__ = '0.2.7'

# some constants to hold the possible responses
ERR_NOTCAPABLE = '500 command not recognized'
ERR_NOPOSTALLOWED = '440 posting not allowed'
ERR_NOPOSTMODE = '201 Hello, you can\'t post'
ERR_CMDSYNTAXERROR = '501 command syntax error (or un-implemented option)'
ERR_NOSUCHGROUP = '411 no such news group'
ERR_NOGROUPSELECTED = '412 no newsgroup has been selected'
ERR_NOARTICLESELECTED = '420 no current article has been selected'
ERR_NOPREVIOUSARTICLE = '422 no previous article in this group'
ERR_NONEXTARTICLE = '421 no next article in this group'
ERR_NOSUCHARTICLENUM = '423 no such article number in this group'
ERR_NOSLAVESHERE = '202 no slaves here please (this is a read-only server)'
ERR_NOSUCHARTICLE = '430 no such article'
ERR_NOIHAVEHERE = '435 article not wanted - do not send it'
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

overview_headers = ('Subject', 'From', 'Date', 'Message-ID', 'References', 'Bytes', 'Lines', 'Xref')

# TODO list:
# ----------
# - MODE STREAM (does this mean 'Connect->command->Close' style conversations?)
# - Check more the patterns of searching (wildmat) -> backend.format_wildcards() -> Work in progress
# - Show banner on the footer of the articles about the site
# - Implement some sort of timeout mechanism
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
    terminated = 0
    selected_article = 'ggg'
    selected_group = 'ggg'
    current_art_id = 0
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
        if len(self.tokens) > 2:
            self.send_response(ERR_CMDSYNTAXERROR)
            return
        if (len(self.tokens) == 2) and (self.tokens[1].upper() == 'OVERVIEW.FMT'):
            self.send_response("%s\r\n%s\r\n." % (STATUS_OVERVIEWFMT, "\r\n".join(["%s:" % k for k in overview_headers])))
            return
        elif len(self.tokens) == 2:
            self.send_response(ERR_CMDSYNTAXERROR)
            return
        result = backend.get_LIST()
        lists = []
        for group_name, table in result:
            total, maximum, minimum = backend.get_group_stats(table)
            lists.append("%s %s %s n" % (group_name, maximum, minimum))
        msg = "%s\r\n%s\r\n." % (STATUS_LIST, "\r\n".join(["%s" % k for k in lists]))
        self.send_response(msg)

    def do_STAT(self):
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
        # check the syntax
        if len(self.tokens) != 2:
            self.send_response(ERR_CMDSYNTAXERROR)
            return
        if self.selected_group == 'ggg':
            self.send_response(ERR_NOGROUPSELECTED)
            return
        # get the article number if it is the appropriate option
        if self.tokens[1].find('@') != -1:
            self.tokens[1] = self.tokens[1][1:self.tokens[1].find('@')]
        head, body = backend.get_ARTICLE(self.selected_group, self.tokens[1])
        response = STATUS_ARTICLE % (self.selected_article, self.selected_group)
        msg = "%s\r\n%s\r\n\r\n%s\r\n." % (response, head, body)
        self.send_response(msg)

    def do_LAST(self):
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
        if self.selected_group == 'ggg':
            self.send_response(ERR_NOGROUPSELECTED)
            return
        if self.selected_article == 'ggg':
            self.send_response(ERR_NOARTICLESELECTED)
            return
        body = backend.get_BODY(self.selected_group, self.selected_article)
        msg = "%s\r\n%s\r\n." % (STATUS_BODY % (self.selected_article, self.selected_article, self.selected_group), body)
        self.send_response(msg)

    def do_HEAD(self):
        if self.selected_group == 'ggg':
            self.send_response(ERR_NOGROUPSELECTED)
            return
        if self.selected_article == 'ggg':
            self.send_response(ERR_NOARTICLESELECTED)
            return
        head = backend.get_HEAD(self.selected_group, self.selected_article)
        msg = "%s\r\n%s\r\n." % (STATUS_HEAD % (self.selected_article, self.selected_article, self.selected_group), head)
        self.send_response(msg)

    def do_XOVER(self):
        """
        Syntax:
        XOVER [range]
        Successfull:
        224 Overview information follows\r\n
        subject\tauthor\tdate\tmessage-id\treferences\tbyte count\tline count\r\n
        Error:
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
        msg = "%s\r\n%s\r\n." % (STATUS_XOVER, overviews)
        self.send_response(msg)

    def do_XPAT(self):
        """
        Syntax:
        XPAT header range|<message-id> pat [pat...]
        Successfull:
        221 Header follows
        
        Error:
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
            self.tokens[2] = self.tokens[2][1:self.tokens[2].find('@')]
            self.do_XHDR()
            return
        else:
            ranges = self.tokens[2].split('-')
            if len(ranges) == 2:
                overviews = backend.get_XPAT(self.selected_group, self.tokens[1], self.tokens[3], ranges[0], ranges[1])
            else:
                overviews = backend.get_XPAT(self.selected_group, self.tokens[1], self.tokens[3], ranges[0])
        msg = "%s\r\n%s\r\n." % (STATUS_XPAT, overviews)
        self.send_response(msg)

    def do_LISTGROUP(self):
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

    def do_XHDR(self):
        """
        Syntax:
        XHDR header [range|<message-id>]
        Replies:
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
                self.tokens[2] = self.tokens[2][1:self.tokens[2].find('@')]
                info = backend.get_XHDR(self.selected_group, self.tokens[1], 'unique', (self.tokens[2]))
            else:
                range = self.tokens[2].split('-')
                if len(range) == 2:
                    info = backend.get_XHDR(self.selected_group, self.tokens[1], 'range', (range[0], range[1]))
                else:
                    info = backend.get_XHDR(self.selected_group, self.tokens[1], 'range', (range[0]))
        # check for empty results
        if info == None:
            self.send_response(ERR_NOSUCHARTICLE)
            return
        msg = "%s\r\n%s\r\n." % (STATUS_XHDR, info)
        self.send_response(msg)

    def do_DATE(self):
        self.send_response(STATUS_DATE % (time.strftime('%Y%m%d%H%M%S', time.localtime(time.time()))))

    def do_HELP(self):
        msg = "%s\r\n\t%s\r\n." % (STATUS_HELPMSG, "\r\n\t".join(self.commands))
        self.send_response(msg)

    def do_QUIT(self):
        self.terminated = 1
        self.send_response(STATUS_CLOSING)

    def do_IHAVE(self):
        self.send_response(ERR_NOIHAVEHERE)

    def do_SLAVE(self):
        self.send_response(ERR_NOSLAVESHERE)

    def do_MODE(self):
        self.send_response(ERR_NOPOSTMODE)

    def do_POST(self):
        self.send_response(ERR_NOPOSTALLOWED)

    def get_timestamp(self, date, times, gmt='yes'):
        local_year = str(time.localtime()[0])
        if date[0:2] >= local_year[2:4]:
            year = "19%s" % (date[0:2])
        else:
            year = "20%s" % (date[0:2])
        ts = time.mktime((int(year), int(date[2:4]), int(date[4:6]), int(times[0:2]), int(times[2:4]), int(times[4:6]), 0, 0, 0))
        if gmt == 'yes':
            return time.gmtime(ts)
        else:
            return time.localtime(ts)

    def send_response(self, message):
        print "Replying:", message
        self.wfile.write(message + "\r\n")
        self.wfile.flush()

    def finish(self):
        print 'Closing the request'
        pass


if __name__ == '__main__':
    # set up signal handler
    def sighandler(signum, frame):
        print "\nClosing the socket..."
        server.socket.close()
        time.sleep(1)
        sys.exit(0)

    from backends.mysql import Papercut_Backend
    backend = Papercut_Backend()

    signal.signal(signal.SIGINT, sighandler)
    print 'Starting the server'
    server = NNTPServer((settings.hostname, 31337), NNTPRequestHandler)
    server.serve_forever()
