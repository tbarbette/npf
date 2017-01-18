#!/usr/bin/python3
import argparse
import time
from email.mime.text import MIMEText
from typing import Tuple, List

from src.regression import *

import smtplib

from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart

class Watcher():
    def __init__(self, repo_list:List[Tuple[Repository,List[Testie]]], mail_to: List[str], mail_from: str, interval: int,mail_always: bool, history: int, quiet:bool):
        self.interval = interval
        self.repo_list = repo_list
        self.mail_to = mail_to
        self.mail_from = mail_from
        self.mail_always = mail_always
        self.history = history
        self.quiet = quiet

    def mail(self,subject, body, images=[], bodytype='text'):
        print(subject)
        COMMASPACE = ', '

        # Create the container (outer) email message.
        msg = MIMEMultipart()
        msg['Subject'] = subject

        if self.mail_from:
            msg['From'] = self.mail_from
        msg['To'] = COMMASPACE.join(self.mail_to)
        msg.attach(MIMEText(body, bodytype))

        for img, cid in images:
            img = MIMEImage(img)
            img.add_header('Content-ID', '<' + cid + '>')
            msg.attach(img)

        s = smtplib.SMTP('localhost')
        s.send_message(msg)
        s.quit()

    def mail_results(self, repo: Repository, build: Build, testies: List[Testie], datasets: List[Dataset],
                     graph_num: int = 0):
        body = '<html>'
        body += 'Detailed results for %s :<br />' % build.uuid

        if not build.build_if_needed():
            self.mail(subject="[%s] Could not compile %s !" % (repo.name, build.uuid), body='')

        graphs = []
        for testie,all_results in zip(testies,datasets):
            body += '<b>%s</b> :' % build.uuid
            if build.n_passed == build.n_tests:
                body += '<span style="color:green;">PASSED</span><br />'
            else:
                print("[%s] Testie %s FAILED !" % (repo.name, testie.filename))
                body += '<span style="color:red;">FAILED</span> with %d/%d points out of constraints.<br />' % (
                    build.n_passed, build.n_tests)
            body += '<img src="cid:%s"><br/><br/>' % testie.filename
            grapher = Grapher()
            graphs_series = [(testie, build, all_results)]

            graphs_series += repo.get_old_results(build, graph_num - len(graphs_series), testie)

            g = grapher.graph(series=graphs_series, title=testie.get_title(),
                              filename=None, graph_variables=list(testie.variables))
            graphs.append((g, testie.filename))

        body += '</html>'

        self.mail(
            subject="[%s] Finished run for %s, %d/%d tests passed" % (
            repo.name, build.uuid, build.n_passed, build.n_tests),
            body=body,
            bodytype='html', images=graphs)

    def run(self):
        terminate = False
        while not terminate:
            for repo, testies in self.repo_list:
                regressor = Regression(repo)
                build,datasets = regressor.regress_all_testies(testies=testies, quiet= self.quiet, history = self.history)

                if (build is None):
                    continue

                if build.n_passed < build.n_tests or self.mail_always:
                    self.mail_results(repo, build, testies, datasets)

            time.sleep(self.interval)


def main():
    parser = argparse.ArgumentParser(description='NPF Watcher')
    parser.add_argument('repos', metavar='repo name', type=str, nargs='+', help='names of the repositories to watch');
    parser.add_argument('--interval', metavar='secs', type=int, nargs=1, default=60,
                        help='interval in seconds between polling of repositories');
    parser.add_argument('--history', dest='history', metavar='N', type=int, default=0,
                        help='assume last N commits as untested (default 0)');
    parser.add_argument('--tags', metavar='tag', type=str, nargs='+', help='list of tags');
    parser.add_argument('--testie', metavar='path or testie', type=str, nargs='?', default='tests',
                        help='script or script folder. Default is tests');
    parser.add_argument('--quiet', help='Quiet mode', dest='quiet', action='store_true', default=False)

    a = parser.add_argument_group('Graphing options')
    a.add_argument('--graph-num', metavar='N', type=int, nargs='?', default=8,
                   help='Number of UUIDs to graph');

    m = parser.add_argument_group('Mail options')
    m.add_argument('--mail-to', metavar='email', type=str, nargs='+', help='list of e-mails for report',
                   default=['tom.barbette@ulg.ac.be']);
    m.add_argument('--mail-from', metavar='email', type=str, nargs=1, dest='mail_from', default='tom.barbette@ulg.ac.be',
                   help='list of e-mails for report');
    m.add_argument('--mail-erroronly', default=True, dest='mail_always',  action='store_false',
                   help='e-mail even if there is an error');
    parser.set_defaults(tags=[])
    args = parser.parse_args();
    history = args.history

    # Parsing repo list and getting last_build
    repo_list = []
    for repo_name in args.repos:
        repo = Repository(repo_name)
        tags = args.tags
        tags += repo.tags

        last_build = repo.get_last_build(history)
        if last_build is not None:
            print("[%s] Last tested uuid is %s" % (repo.name, last_build.uuid))
        repo.last_build = last_build

        testies = Testie.expand_folder(args.testie, tags=tags, quiet=args.quiet)
        repo_list.append((repo, testies))

    watcher = Watcher(repo_list,
                      mail_from=args.mail_from,
                      mail_to=args.mail_to,
                      interval = args.interval,
                      mail_always = args.mail_always,
                      history = history,
                      quiet = args.quiet)
    watcher.run()


if __name__ == "__main__":
    main()
