#!/usr/bin/env python3
"""
NPF repository watcher. Essentially a loop watching for commits in a list of git repo to execute given tests when
a commit is made. If you want to integrate npf in your CI test suite, use npf-run. Passive watching is intended
to watch project you don't own but you use, just to be sure that they do not mess performances.

We prefered to separate this tool from npf-run because of the lot of specifics for sending an e-mail, watch loop, etc
"""
import argparse
import smtplib
import time
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import sys

from npf import npf
from npf.regression import *
from npf.test import Test


class Watcher():
    def __init__(self, repo_list:List[Tuple[Repository,List[Test]]], mail_to: List[str], mail_from: str, mail_smtp : str, interval: int,
                 mail_always: bool, history: int, options):
        self.interval = interval
        self.repo_list = repo_list
        self.mail_to = mail_to
        self.mail_from = mail_from
        self.mail_always = mail_always
        self.mail_smtp = mail_smtp
        self.history = history
        self.options = options


    def mail(self, subject, body, images=None, bodytype='text'):
        if not self.mail_to:
            return
        if images is None:
            images = []

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

        s = smtplib.SMTP(self.mail_smtp)
        s.send_message(msg)
        s.quit()

    def mail_results(self, repo: Repository, build: Build, tests: List[Test], datasets: List[Dataset],
                     graph_num: int = 0):
        ext = 'png'
        body = '<html>'
        body += 'Detailed results for %s :<br />' % build.version

        if not build.build():
            self.mail(subject="[%s] Could not compile %s !" % (repo.name, build.version), body='')

        graphs = []
        for test,all_results in zip(tests,datasets):
            body += '<b>%s</b> :' % build.version
            if test.n_variables_passed == test.n_variables:
                body += '<span style="color:green;">PASSED</span><br />'
            else:
                print("[%s] Test %s FAILED !" % (repo.name, test.filename))
                body += '<span style="color:red;">FAILED</span> with %d/%d points in constraints.<br />' % (
                    test.n_variables_passed, test.n_variables)

            grapher = Grapher()
            graphs_series = [(test, build, all_results)]

            graphs_series += repo.get_old_results(build, graph_num - len(graphs_series), test)

            gs = grapher.graph(series=graphs_series, title=test.get_title(),
                              filename=None, graph_variables=[Run(x) for x in test.variables],
                              options=self.options)

            for result_type,g in gs.items():
                fname = test.filename + "-" + result_type + "." + ext
                body += '<img src="cid:%s"><br/>' % (fname)
                graphs.append((g, fname))

            body += '<br/>';

        body += '</html>'

        self.mail(
            subject="[%s] Finished run for %s, %d/%d tests passed" % (
            repo.name, build.version, build.n_passed, build.n_tests),
            body=body,
            bodytype='html', images=graphs)

    def run(self,options):
        terminate = False
        while not terminate:
            for repo, tests in self.repo_list:
                build = repo.get_last_build(with_results=False,force_fetch=(self.history==1))
                if repo.last_build.version == build.version:
                    if not options.quiet:
                        print("[%s] Last version is %s, no changes." % (repo.name,build.version))
                    continue

                regressor = Regression(repo)

                build,datasets,time_datasets = regressor.regress_all_tests(tests=tests, options=options, history = self.history)

                if (build is None):
                    continue

                if self.history == 1 and (build.n_passed < build.n_tests or self.mail_always):
                    self.mail_results(repo, build, tests, datasets)

            if self.history > 1:
                self.history -= 1
            else:
                if options.onerun:
                    terminate = True
                    break
                time.sleep(self.interval)


def main():
    parser = argparse.ArgumentParser(description='NPF Watcher')
    parser.add_argument('repos', metavar='repo name', type=str, nargs='+', help='names of the repositories to watch')
    parser.add_argument('--interval', metavar='secs', type=int, nargs=1, default=60,
                        help='interval in seconds between polling of repositories')
    parser.add_argument('--history', dest='history', metavar='N', type=int, default=1,
                        help='assume last N commits as untested (default 0)')

    v = npf.add_verbosity_options(parser)

    t = npf.add_testing_options(parser)

    b = npf.add_building_options(parser)

    a = npf.add_graph_options(parser)
    a.add_argument('--graph-num', metavar='N', type=int, nargs='?', default=8,
                   help='Number of versions to graph')

    m = parser.add_argument_group('Mail options')
    m.add_argument('--mail-to', metavar='email', type=str, nargs='+', help='list of e-mails for report',
                   default=[])
    m.add_argument('--mail-from', metavar='email', type=str, nargs=1, dest='mail_from', default='tom.barbette@ulg.ac.be',
                   help='list of e-mails for report')
    m.add_argument('--mail-erroronly', default=True, dest='mail_always',  action='store_false',
                   help='e-mail even if there is an error')
    m.add_argument('--mail-smtp', metavar='address', type=str, dest='mail_smtp', default='localhost',
                   help='smtp server address. Default is localhost')

    m.add_argument('--onerun', default=False, dest='onerun',  action='store_true',
                   help='Do only one loop of regression test, usefull for testing that this software mainly works')

    parser.set_defaults(graph_size=[6,2.5])
    args = parser.parse_args()

    npf.parse_nodes(args)

    history = args.history

    if len(args.mail_to) == 0:
        print("Warning: No mail-to e-mail address given. NPF Watcher will not send any e-mail.")

    # Parsing repo list and getting last_build
    repo_list = []
    for repo_name in args.repos:
        repo = Repository.get_instance(repo_name, args)
        tags = args.tags.copy()
        tags += repo.tags

        last_build = repo.get_last_build(history, with_results=True)
        if last_build is not None:
            print("[%s] Last tested version is %s" % (repo.name, last_build.version))
        repo.last_build = last_build

        tests = Test.expand_folder(args.test_files, tags=tags,options=args)

        if len(tests) == 0:
            print("[%s] No valid tests. Ignoring this repo." % (repo.name))
        else:
            repo_list.append((repo, tests))

    if len(repo_list) == 0:
        print("ERROR : No valid repositories to use !")
        sys.exit(-1)

    watcher = Watcher(repo_list,
                      mail_from=args.mail_from,
                      mail_to=args.mail_to,
                      interval = args.interval,
                      mail_always = args.mail_always,
                      mail_smtp = args.mail_smtp,
                      history = history,
                      options=args)
    watcher.run(args)


if __name__ == "__main__":
    main()
