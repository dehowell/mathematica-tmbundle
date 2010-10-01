#!/usr/bin/env python
import os
import sys
import time
import string
import socket
import shutil
import subprocess
import traceback
import plistlib
from optparse import OptionParser

def exit_discard():
    sys.exit(200)

def exit_replace_text(out = None):
    if out is not None:
        sys.stdout.write(out)
    sys.exit(201)

def exit_replace_document(out = None):
    if out is not None:
        sys.stdout.write(out)
    sys.exit(202)

def exit_insert_text(out = None):
    if out is not None:
        sys.stdout.write(out)
    sys.exit(203)

def exit_insert_snippet(out = None):
    if out is not None:
        sys.stdout.write(out)
    sys.exit(204)

def exit_show_html(out = None):
    if out is not None:
        sys.stdout.write(out)
    sys.exit(205)

def exit_show_tool_tip(out = None):
    if out is not None:
        sys.stdout.write(out)
    sys.exit(206)

def exit_create_new_document(out = None):
    if out is not None:
        sys.stdout.write(out)
    sys.exit(207)

def return_focus_to_textmate():
    osascript = """
        tell application "TextMate"
        	activate
        	tell application "System Events" to keystroke "`" using {command down, shift}
        end tell
    """
    # subprocess.call(["osascript", "-e", osascript])

class MathMate(object):
    def __init__(self, input_file = None, process_entire_document = False):
        self.cacheFolder = '/tmp/tmjlink'
        self.mlargs = ["-linkmode", "launch", "-linkname", "/Applications/Mathematica.app/Contents/MacOS/MathKernel", "-mathlink"]
        
        self.parse_tree_level = None
        
        if input_file is None:
            self.doc = sys.stdin.read()
        else:
            fp = open(input_file, 'r')
            self.doc = fp.read()
            fp.close()
        
        self.indent_size = int(os.environ['TM_TAB_SIZE'])
        if os.environ.get('TM_SOFT_TABS') == "YES":
            self.indent = " " * self.indent_size
        elif os.environ.get('TM_SOFT_TABS') == "NO":
            self.indent = "\t"
        
        self.tmln = int(os.environ.get('TM_LINE_NUMBER'))
        self.tmli = int(os.environ.get('TM_LINE_INDEX'))
        self.tmcursor = self.get_pos(self.tmln, self.tmli)
        self.selected_text = os.environ.get('TM_SELECTED_TEXT')
        self.process_entire_document = process_entire_document
        self.statements = self.parse(self.doc)
            
        sessid = os.path.split(os.environ.get('TM_FILEPATH', 'mathmate-default'))[-1]
        if sessid.endswith(".m"):
            self.sessid = sessid[:-2]
        else:
            self.sessid = sessid
    
    def shutdown(self):
        pidfile = os.path.join(self.cacheFolder, "tmjlink.pid")
        if os.path.exists(pidfile):
            try:
                pidfp = open(pidfile, 'r')
                pid = int(pidfp.read())
                pidfp.close()
                os.kill(pid, 1)
                return "TextMateJLink Server Shutdown"
            except:
                pass
        return "TextMateJLink Server is not Running"
    
    def is_tmjlink_alive(self):
        pidfile = os.path.join(self.cacheFolder, "tmjlink.pid")
        if os.path.exists(pidfile):
            try:
                pidfp = open(pidfile, 'r')
                pid = int(pidfp.read())
                pidfp.close()
                
                os.kill(pid, 0)
                return True
            except:
                pass
        return False
    
    def get_textmate_pid(self):
        current_pid = os.getpid()
        while current_pid != 1:
            shell = subprocess.Popen(["ps", "-p", str(current_pid), "-o", "pid,ppid,command"], stdout=subprocess.PIPE)
            process = map(lambda x: x[:11].split() + [x[12:]], shell.stdout.read().rstrip().split("\n"))[1]
            if "TextMate.app/Contents/MacOS/TextMate" in process[2]:
                return current_pid
            current_pid = int(process[1])
        raise Exception("Could not determine TextMate.app pid.")

    def launch_tmjlink(self):
        if self.is_tmjlink_alive():
            return
        
        classpath = []
        classpath.append(os.path.join(os.environ.get('TM_BUNDLE_SUPPORT'), "tmjlink"))
        classpath.append("/Applications/Mathematica.app/SystemFiles/Links/JLink/JLink.jar")
        
        if os.path.exists(self.cacheFolder):
           shutil.rmtree(self.cacheFolder) 
        os.mkdir(self.cacheFolder, 0777)
        
        # Launch TextMateJLink
        textmate_pid = self.get_textmate_pid()
        logfp = open(os.path.join(self.cacheFolder, "tmjlink.log"), 'w')
        proc = subprocess.Popen(['/usr/bin/java', 
                '-cp', ":".join(classpath), 
                'com.shadanan.textmatejlink.TextMateJLink', 
                self.cacheFolder, str(textmate_pid)] + self.mlargs,
            stdout=logfp, stderr=subprocess.STDOUT)
        logfp.close()
        
        # Save PID file
        pidfp = open(os.path.join(self.cacheFolder, "tmjlink.pid"), 'w')
        pidfp.write(str(proc.pid))
        pidfp.close()
    
    def readtotal(self, sock, count):
        result = []
        total_read = 0
        
        while total_read != count:
            buff = sock.recv(count - total_read)
            
            if buff == "":
                raise Exception("The server quit unexpectedly.")
                
            result.append(buff)
            total_read += len(buff)
        
        return "".join(result)
    
    def readline(self, sock):
        result = []
        while True:
            char = sock.recv(1)
            
            if char == "\r":
                continue
                
            if char == "\n":
                break
                
            if char == "":
                return None
                
            result.append(char)
            
        return "".join(result)
    
    def connect(self):
        self.launch_tmjlink()
        
        # Wait for server to be ready and get listen port
        logfp = open(os.path.join(self.cacheFolder, "tmjlink.log"), 'r')
        while True:
            line = logfp.readline()
            if line == "":
                time.sleep(0.1)
                continue
            if line.strip().startswith("Server started on port: "):
                port = int(line.strip()[24:])
                break
        logfp.close()
    
        sock = socket.socket()
        sock.connect(("localhost", port))
        return sock
    
    def read(self, sock):
        line = self.readline(sock)

        if line is None:
            raise Exception("The server quit unexpectedly.")
            
        if line.find(" -- ") != -1:
            response = line[0:line.find(" -- ")]
            comment = line[line.find(" -- ")+4:]
        else:
            response = line
            comment = None
            
        words = response.split(" ")
        return (line, response, words, comment)
    
    def inline(self, force_image = False):
        # Output header (stylesheet, js, etc)
        sys.stdout.write("""
          <?xml version="1.0" encoding="UTF-8"?>
          <!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN"
            "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
        
          <html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">
            <head>
              <title>TextMate Mathematica Output</title>
        
              <link rel="stylesheet" href="file://%(tm_bundle_support)s/web/tmjlink.css" type="text/css" media="screen" charset="utf-8">
              <script type="text/javascript" src="file://%(tm_bundle_support)s/web/jquery-1.4.2.min.js" charset="utf-8"></script>
            </head>
            <body>
              <div class="header">
                <div class="text">
                  <span class="purple">TextMate</span><span class="white">Mathematica</span>
                  <br style="clear:both" />
                </div>
              </div>
        """ % {"tm_bundle_support": os.environ.get('TM_BUNDLE_SUPPORT')})
        sys.stdout.flush()
        
        try:
            sock = self.connect()

            statements = []
            if self.selected_text is not None or self.process_entire_document:
                for ssp, esp, reformatted_statement, current_statement in self.statements:
                    statements.append(current_statement)
            else:
                ssp, esp, reformatted_statement, current_statement = self.get_current_statement()
                statements.append(current_statement)

            state = 0
            readsize = None
            while True:
                if readsize is not None:
                    content = self.readtotal(sock, readsize)
                else:
                    line, response, words, comment = self.read(sock)

                if state == 0:
                    if response == "okay":
                        sock.send("sessid %s\n" % self.sessid)
                        state = 1
                        continue

                    if response == "exception":
                        raise Exception("TextMateJLink Exception: " + comment)

                    raise Exception("Unexpected message from JLink server: " + line)
            
                if state == 1:
                    if response == "okay":
                        sock.send("header\n")
                        state = 3
                        continue
                    
                    if response == "exception":
                        raise Exception("TextMateJLink Exception: " + comment)

                    raise Exception("Unexpected message from JLink server: " + line)
            
                if state == 2:
                    if response == "okay":
                        if len(statements) == 0:
                            sock.send("quit\n")
                            state = 5
                            continue
                    
                        statement = statements.pop(0).rstrip()
                        if force_image:
                            sock.send("image %d\n" % len(statement))
                        else:
                            sock.send("execute %d\n" % len(statement))
                        sock.send(statement)
                        state = 3
                        continue

                    if response == "exception":
                        raise Exception("TextMateJLink Exception: " + comment)

                    raise Exception("Unexpected message from JLink server: " + line)
            
                if state == 3:
                    if words[0] == "inline":
                        readsize = int(words[1])
                        state = 4
                        continue
                    
                    if response == "exception":
                        raise Exception("TextMateJLink Exception: " + comment)

                    raise Exception("Unexpected message from JLink server: " + line)
            
                if state == 4:
                    sys.stdout.write(content)
                    sys.stdout.flush()
                    readsize = None
                    state = 2
                    continue
            
                if state == 5:
                    if response == "okay":
                        sock.close()
                        break

                    if response == "exception":
                        raise Exception("TextMateJLink Exception: " + comment)

                    raise Exception("Unexpected message from JLink server: " + line)

                raise Exception("Invalid state: " + state)
            
        except Exception:
            sys.stdout.write('<div class="exception">%s</div>' % traceback.format_exc())
            sys.stdout.flush()
            
        # Footer (closing tags, etc)
        sys.stdout.write("""
              <script type="text/javascript" charset="utf-8">
                $(window).load(function() {
                  $(window).scrollTop($(document).height());
                });
        
                $('#white_space .value').click(function() {
                  if ($(this).html() == "Normal") {
                    $(this).html("Pre");
                    $('div.cell div.content').css('white-space', 'pre');
                  } else {
                    $(this).html("Normal");
                    $('div.cell div.content').css('white-space', 'normal');
                  }
                });
        
                function toggle(resource_id) {
                  $('#resource_' + resource_id + ' .return').toggle();
                }
              </script>
            </body>
          </html>
        """)
        sys.stdout.flush()

    def clear(self):
        sock = self.connect()
        
        state = 0
        while True:
            line, response, words, comment = self.read(sock)
            
            if state == 0:
                if response == "okay":
                    sock.send("sessid %s\n" % self.sessid)
                    state = 1
                    continue
            
                if response == "exception":
                    raise Exception("TextMateJLink Exception: " + comment)

                raise Exception("Unexpected message from JLink server: " + line)
                
            if state == 1:
                if response == "okay":
                    sock.send("clear\n")
                    state = 2
                    continue
                        
                if response == "exception":
                    raise Exception("TextMateJLink Exception: " + comment)

                raise Exception("Unexpected message from JLink server: " + line)
            
            if state == 2:
                if response == "okay":
                    sock.send("quit\n")
                    state = 3
                    continue
            
                if response == "exception":
                    raise Exception("TextMateJLink Exception: " + comment)

                raise Exception("Unexpected message from JLink server: " + line)
                
            if state == 3:
                if response == "okay":
                    sock.close()
                    break
            
                if response == "exception":
                    raise Exception("TextMateJLink Exception: " + comment)

                raise Exception("Unexpected message from JLink server: " + line)
            
            raise Exception("Invalid state: " + state)
        
        return "Session Cleared"
            
    def reset(self):
        sock = self.connect()

        state = 0
        while True:
            line, response, words, comment = self.read(sock)

            if state == 0:
                if response == "okay":
                    sock.send("sessid %s\n" % self.sessid)
                    state = 1
                    continue

                if response == "exception":
                    raise Exception("TextMateJLink Exception: " + comment)

                raise Exception("Unexpected message from JLink server: " + line)

            if state == 1:
                if response == "okay":
                    sock.send("reset\n")
                    state = 2
                    continue

                if response == "exception":
                    raise Exception("TextMateJLink Exception: " + comment)

                raise Exception("Unexpected message from JLink server: " + line)

            if state == 2:
                if response == "okay":
                    sock.send("quit\n")
                    state = 3
                    continue

                if response == "exception":
                    raise Exception("TextMateJLink Exception: " + comment)

                raise Exception("Unexpected message from JLink server: " + line)

            if state == 3:
                if response == "okay":
                    sock.close()
                    break

                if response == "exception":
                    raise Exception("TextMateJLink Exception: " + comment)

                raise Exception("Unexpected message from JLink server: " + line)

            raise Exception("Invalid state: " + state)

        return "Session Reset"

    def get_symbols(self):
        sock = self.connect()

        state = 0
        while True:
            line, response, words, comment = self.read(sock)

            if state == 0:
                if response == "okay":
                    sock.send("sessid %s\n" % self.sessid)
                    state = 1
                    continue

                if response == "exception":
                    raise Exception("TextMateJLink Exception: " + comment)

                raise Exception("Unexpected message from JLink server: " + line)

            if state == 1:
                if response == "okay":
                    sock.send("suggest\n")
                    state = 2
                    continue

                if response == "exception":
                    raise Exception("TextMateJLink Exception: " + comment)

                raise Exception("Unexpected message from JLink server: " + line)

            if state == 2:
                if words[0] == "suggestions":
                    result = eval(words[1])
                    sock.send("quit\n")
                    state = 3
                    continue

                if response == "exception":
                    raise Exception("TextMateJLink Exception: " + comment)

                raise Exception("Unexpected message from JLink server: " + line)

            if state == 3:
                if response == "okay":
                    sock.close()
                    break

                if response == "exception":
                    raise Exception("TextMateJLink Exception: " + comment)

                raise Exception("Unexpected message from JLink server: " + line)

            raise Exception("Invalid state: " + state)

        return result

    def get_pos(self, line, column):
        line_index = 1
        line_pos = 0
    
        for pos, char in enumerate(self.doc):
            if line == line_index and column == pos - line_pos:
                return pos
        
            if char == "\n":
                line_index += 1
                line_pos = pos + 1
        
        return len(self.doc)
        
    def get_line_col(self, posq):
        line_index = 1
        line_pos = 0
        
        for pos, char in enumerate(self.doc):
            if posq == pos:
                return (line_index, pos - line_pos)
        
            if char == "\n":
                line_index += 1
                line_pos = pos + 1
        
        return (line_index, pos - line_pos)

    def count_indents(self, line):
        count = 0
        space_count = 0

        for char in line.rstrip():
            if char == "\t":
                count += 1
            elif char == " ":
                space_count = ((space_count + 1) % self.indent_size)
                if space_count == 0:
                    count += 1
            else:
                break
        return count
    
    def get_next_non_space_char(self, pos):
        for i in xrange(pos, len(self.doc)):
            if self.doc[i] in (" ", "\t"):
                continue
            if self.doc[i] == "\n":
                return None
            return self.doc[i]
        return None
    
    def get_prev_non_space_char(self, pos):
        for i in xrange(pos, -1, -1):
            if self.doc[i] in (" ", "\t"):
                continue
            if self.doc[i] == "\n":
                return None
            return self.doc[i]
        return None

    def is_end_of_line(self, pos):
        return self.get_next_non_space_char(pos) == None
    
    def parse(self, block, initial_indent_level = None):
        statements = []
        
        pos = 0
        ss_pos = 0
        current = []
        scope = []
        
        if initial_indent_level is None:
            initial_indent_level = self.count_indents(block)
        
        while pos < len(block):
            c1 = block[pos]
            c2 = block[pos:pos+2]
            c3 = block[pos:pos+3]
            pc = block[pos-1] if pos > 0 else None

            nnsc = None
            for i in xrange(pos + 1, len(block)):
                if block[i] == "\n":
                    break
                    
                if block[i] not in (" ", "\t"):
                    nnsc = block[i]
                    break

            if pos == self.tmcursor:
                self.parse_tree_level = ".".join(scope)

            if len(scope) == 0:
                if c1 != "\n" and nnsc is not None:
                    if current != []:
                        statements.append((ss_pos, pos, "".join(current), block[ss_pos:pos]))
                        current = []

                    ss_pos = pos
                    scope.append("root")
                    
                    indent_level = len(scope) + initial_indent_level - 1
                    if nnsc in ("]", "}", ")"):
                        current += (self.indent * (indent_level - 1))
                    else:
                        current += (self.indent * indent_level)
                    
                    while block[pos] in (" ", "\t"):
                        pos += 1
                    continue
                
                if c1 in (" ", "\t") and nnsc is not None:
                    ss_pos = pos
                    scope.append("root")
                    
                    indent_level = len(scope) + initial_indent_level - 1
                    if nnsc in ("]", "}", ")"):
                        current += (self.indent * (indent_level - 1))
                    else:
                        current += (self.indent * indent_level)
                    
                    while block[pos] in (" ", "\t"):
                        pos += 1
                    continue
                    
                current += c1
                pos += 1
                continue

            if scope[-1] == "string":
                if c2 == '\\"':
                    current += c2
                    pos += 2
                    continue

                if c1 == '"':
                    scope.pop()
                    current += c1
                    pos += 1
                    continue

                current += c1
                pos += 1
                continue

            if scope[-1] == "comment":
                if c3 == '\\*)':
                    current += c3
                    pos += 3
                    continue
                
                if c2 == '(*':
                    scope.append("comment")
                    current += c2
                    pos += 2
                    continue
                
                if c2 == '*)':
                    scope.pop()
                    current += c2
                    pos += 2
                    continue

                current += c1
                pos += 1
                continue

            if c1 in (" ", "\t"):
                vsc = string.ascii_letters + string.digits
                if pc is not None and nnsc is not None and pc in (vsc + "]})") and nnsc in vsc:
                    current += " "
                pos += 1
                continue
        
            if c3 in ("===", ">>>", "^:="):
                if self.is_end_of_line(pos + 3):
                    scope += ("binop", "start")
                current += " ", c3, " "
                pos += 3
                continue

            if c3 == "@@@":
                if self.is_end_of_line(pos + 3):
                    scope += ("binop", "start")
                current += c3
                pos += 3
                continue

            if c2 in ("*^", "&&", "||", "==", ">=", "<=", ";;", "/.", "->", ":>", "<>", ">>", "/@", "/;", "//", "~~", ":=", "^="):
                if self.is_end_of_line(pos + 2):
                    scope += ("binop", "start")
                current += " ", c2, " "
                pos += 2
                continue
            
            if c2 == "@@":
                if self.is_end_of_line(pos + 2):
                    scope += ("binop", "start")
                current += c2
                pos += 2
                continue

            if c2 == "..":
                current += c2, " "
                pos += 2
                continue

            if c2 == "(*":
                scope.append("comment")
                current += c2
                pos += 2
                continue

            if c2 == "[[":
                scope.append("part")
                current += c2
                pos += 2
                continue
        
            if c2 == "]]" and scope[-1] == "part":
                while scope[-1] == "binop":
                    scope.pop()
                scope.pop()
                current += c2
                pos += 2
                continue
        
            if c1 == "[":
                scope.append("function")
                current += c1
                pos += 1
                continue
        
            if c1 == "]":
                while scope[-1] == "binop":
                    scope.pop()
                scope.pop()
                current += c1
                pos += 1
                continue
        
            if c1 == "{":
                scope.append("list")
                current += c1
                pos += 1
                continue
        
            if c1 == "}":
                while scope[-1] == "binop":
                    scope.pop()
                scope.pop()
                current += c1
                pos += 1
                continue
        
            if c1 == "(":
                scope.append("group")
                current += c1
                pos += 1
                continue
        
            if c1 == ")":
                while scope[-1] == "binop":
                    scope.pop()
                scope.pop()
                current += c1
                pos += 1
                continue
            
            if c1 == "!":
                current += c1, " "
                pos += 1
                continue
                
            if c1 == "?":
                current += c1
                pos += 1
                continue
            
            if c1 in ("*", "/", "^"):
                if self.is_end_of_line(pos + 1):
                    scope += ("binop", "start")
                current += c1
                pos += 1
                continue
            
            if c1 in ("+", ">", "<", "|", "="):
                if self.is_end_of_line(pos + 1):
                    scope += ("binop", "start")
                current += " ", c1, " "
                pos += 1
                continue
            
            if c1 == "-":
                if self.is_end_of_line(pos + 1):
                    scope += ("binop", "start")
                    
                if self.get_prev_non_space_char(pos-1) not in (None, "{", "(", "[", ","):
                    current += " ", c1, " "
                else:
                    current += c1
                pos += 1
                continue

            if c1 == "&":
                current += " ", c1
                pos += 1
                continue
            
            if c1 == ",":
                while scope[-1] == "binop":
                    scope.pop()
                current += c1, " "
                pos += 1
                continue

            if c1 == ";":
                while scope[-1] == "binop":
                    scope.pop()
                if scope[-1] == "root":
                    scope.pop()
                current += c1
                pos += 1
                continue

            if c1 == "\n":
                while scope[-1] == "binop":
                    scope.pop()
                if scope[-1] == "start":
                    scope.pop()
                if scope[-1] == "root":
                    scope.pop()
                current += c1
                pos += 1

                indent_level = len(scope) + initial_indent_level - 1
                if nnsc in ("]", "}", ")"):
                    current += (self.indent * (indent_level - 1))
                else:
                    current += (self.indent * indent_level)

                continue
                
            if c1 == '"':
                scope.append("string")
                current += c1
                pos += 1
                continue
            
            if pc is not None and pc in "]})" and c1 in vsc:
                current += " "
            
            current += c1
            pos += 1
            continue

        if current != []:
            statements.append((ss_pos, pos, "".join(current), block[ss_pos:pos]))
        return statements
    
    def get_current_statement_index(self):
        for index, (ssp, esp, reformatted_statement, current_statement) in enumerate(self.statements):
            if self.tmcursor >= ssp and self.tmcursor < esp:
                return index
        return len(self.statements) - 1
            
    def get_current_statement(self):
        return self.statements[self.get_current_statement_index()]
    
    def reformat(self):
        if self.selected_text is not None or self.process_entire_document:
            result = []
            
            for ssp, esp, reformatted_statement, current_statement in self.statements:
                result.append(reformatted_statement)
            
            if "".join(result) == self.doc:
                exit_show_tool_tip("No reformat required.")
            else:
                exit_replace_text("".join(result))
        else:
            result = []
            
            ssp, esp, reformatted_statement, current_statement = self.get_current_statement()
            result.append(self.doc[0:ssp])
            result.append(reformatted_statement)
            result.append(self.doc[esp:])
            
            if "".join(result) == self.doc:
                exit_show_tool_tip("No reformat required.")
            else:
                exit_replace_document("".join(result))

    def show(self):
        result = []
        result.append("Cursor: (Line: %d, Index: %d, Pos: %s, Tree: %s)" % (self.tmln, self.tmli, self.tmcursor, self.parse_tree_level))

        if self.selected_text is None and not self.process_entire_document:
            ssp, esp, reformatted_statement, current_statement = self.get_current_statement()
            ssln, ssli = self.get_line_col(ssp)
            esln, esli = self.get_line_col(esp)
            result.append("Statement Boundaries: (Line: %d, Index: %d) -> (Line: %d, Index: %d)" % (ssln, ssli, esln, esli))
            result.append(reformatted_statement)
        else:
            for index, (ssp, esp, reformatted_statement, current_statement) in enumerate(self.statements):
                ssln, ssli = self.get_line_col(ssp)
                esln, esli = self.get_line_col(esp)
                result.append("Statement %d Boundaries: (Line: %d, Index: %d) -> (Line: %d, Index: %d)" % (index, ssln, ssli, esln, esli))
                if len(reformatted_statement.strip()) != 0:
                    result.append(reformatted_statement.rstrip())
                else:
                    result.append("*** Empty Statement ***")
                result.append("")

        return "\n".join(result)
    
    def suggest(self):
        # Get currently typed function
        fnname = []
        vfcs = string.ascii_letters + string.digits + "$"
        pos = self.tmcursor - 1
        
        while pos >= 0:
            if self.doc[pos] not in vfcs:
                break
            fnname.insert(0, self.doc[pos])
            pos -= 1
        
        while len(fnname) > 0 and fnname[0] in string.digits:
            fnname.pop(0)
        
        fnname = "".join(fnname)
        
        suggestions = filter(lambda x: x != "?" and x.startswith(fnname), self.get_symbols())
        
        if len(suggestions) == 0:
            exit_show_tool_tip("No suggestions.")
        
        data = {}
        data['suggestions'] = map(lambda x: {'display': x}, suggestions)
        
        command = [os.environ.get('DIALOG'), "popup", "--alreadyTyped", fnname]
        proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        proc.stdin.write(plistlib.writePlistToString(data))
        proc.stdin.close()
        
        out = proc.stdout.read()
        if out != "":
            exit_show_tool_tip(out)
        exit_discard()

def main():
    parser = OptionParser()
    parser.add_option("-i", "--force_image", dest="force_image", default=False, action="store_true",
                      help="Render everything as gif files.")
    (options, args) = parser.parse_args()
    command = args[0]
    
    input_file = None
    if len(args) == 2:
        input_file = args[1]
    
    try:
        if command == "show":
            mm = MathMate(input_file)
            exit_show_tool_tip(mm.show())
    
        if command == "inline":
            mm = MathMate(input_file)
            mm.inline(force_image=options.force_image)
            return_focus_to_textmate()
            exit_show_html()
        
        if command == "execute":
            mm = MathMate(input_file, process_entire_document=True)
            mm.reset()
            mm.inline()
            return_focus_to_textmate()
            exit_show_html()
    
        if command == "clear":
            mm = MathMate(input_file)
            exit_show_tool_tip(mm.clear())
    
        if command == "reset":
            mm = MathMate(input_file)
            exit_show_tool_tip(mm.reset())
    
        if command == "shutdown":
            mm = MathMate(input_file)
            exit_show_tool_tip(mm.shutdown())
    
        if command == "reformat":
            mm = MathMate(input_file)
            mm.reformat()
        
        if command == "complete":
            mm = MathMate(input_file)
            mm.suggest()
        
    except Exception:
        stacktrace = traceback.format_exc()
        exit_show_tool_tip(stacktrace)
    
    exit_show_tool_tip("Command not recognized: %s" % command)

if __name__ == '__main__':
    main()