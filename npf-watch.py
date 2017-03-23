#!/usr/bin/python3
"""
NPF repository watcher. Essencially a loop watching for commits in a list of git repo to execute given testies when
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

from npf import args
from npf.regression import *
from npf.testie import Testie


class Watcher():
    def __init__(self, repo_list:List[Tuple[Repository,List[Testie]]], mail_to: List[str], mail_from: str, interval: int,
                 mail_always: bool, history: int, options):
        self.interval = interval
        self.repo_list = repo_list
        self.mail_to = mail_to
        self.mail_from = mail_from
        self.mail_always = mail_always
        self.history = history
        self.options = options


    def mail(self, subject, body, images=None, bodytype='text'):
        if images is None:
            images = []
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
        body += 'Detailed results for %s :<br />' % build.version

        if not build.build():
            self.mail(subject="[%s] Could not compile %s !" % (repo.name, build.version), body='')

        graphs = []
        for testie,all_results in zip(testies,datasets):
            body += '<b>%s</b> :' % build.version
            if testie.n_variables_passed == testie.n_variables:
                body += '<span style="color:green;">PASSED</span><br />'
            else:
                print("[%s] Testie %s FAILED !" % (repo.name, testie.filename))
                body += '<span style="color:red;">FAILED</span> with %d/%d points in constraints.<br />' % (
                    testie.n_variables_passed, testie.n_variables)
            body += '<img npf="cid:%s"><br/><br/>' % testie.filename
            grapher = Grapher()
            graphs_series = [(testie, build, all_results)]

            graphs_series += repo.get_old_results(build, graph_num - len(graphs_series), testie)

            g = grapher.graph(series=graphs_series, title=testie.get_title(),
                              filename=None, graph_variables=[Run(x) for x in testie.variables],
                              options=self.options)
            graphs.append((g, testie.filename))

        body += '</html>'

        self.mail(
            subject="[%s] Finished run for %s, %d/%d tests passed" % (
            repo.name, build.version, build.n_passed, build.n_tests),
            body=body,
            bodytype='html', images=graphs)

    def run(self,options):
        terminate = False
        while not terminate:
            for repo, testies in self.repo_list:
                build = repo.get_last_build(with_results=False)
                if (repo.last_build.version == build.version):
                    if not options.quiet:
                        print("[%s] Last version is %s, no changes." % (repo.name,build.version))
                    continue

                regressor = Regression(repo)
                build,datasets = regressor.regress_all_testies(testies=testies, options=options, history = self.history)

                if (build is None):
                    continue

                if build.n_passed < build.n_tests or self.mail_always:
                    self.mail_results(repo, build, testies, datasets)

            time.sleep(self.interval)


def main():
    parser = argparse.ArgumentParser(description='NPF Watcher')
    parser.add_argument('repos', metavar='repo name', type=str, nargs='+', help='names of the repositories to watch')
    parser.add_argument('--interval', metavar='secs', type=int, nargs=1, default=60,
                        help='interval in seconds between polling of repositories')
    parser.add_argument('--history', dest='history', metavar='N', type=int, default=1,
                        help='assume last N commits as untested (default 0)')

    v = args.add_verbosity_options(parser)

    t = args.add_testing_options(parser)

    a = args.add_graph_options(parser)
    a.add_argument('--graph-num', metavar='N', type=int, nargs='?', default=8,
                   help='Number of versions to graph')

    m = parser.add_argument_group('Mail options')
    m.add_argument('--mail-to', metavar='email', type=str, nargs='+', help='list of e-mails for report',
                   default=['tom.barbette@ulg.ac.be'])
    m.add_argument('--mail-from', metavar='email', type=str, nargs=1, dest='mail_from', default='tom.barbette@ulg.ac.be',
                   help='list of e-mails for report')
    m.add_argument('--mail-erroronly', default=True, dest='mail_always',  action='store_false',
                   help='e-mail even if there is an error')

    args = parser.parse_args()

    args.parse_nodes(args)

    history = args.history

    # Parsing repo list and getting last_build
    repo_list = []
    for repo_name in args.repos:
        repo = Repository.get_instance(repo_name)
        tags = args.tags.copy()
        tags += repo.tags

        last_build = repo.get_last_build(history, with_results=True)
        if last_build is not None:
            print("[%s] Last tested version is %s" % (repo.name, last_build.version))
        repo.last_build = last_build

        testies = Testie.expand_folder(args.testie, tags=tags,options=args)
        if len(testies) == 0:
            print("[%s] No valid testies. Ignoring this repo." % (repo.name))
        else:
            repo_list.append((repo, testies))

    if len(repo_list) == 0:
        print("ERROR : No valid repositories to use !")
        sys.exit(-1)

    watcher = Watcher(repo_list,
                      mail_from=args.mail_from,
                      mail_to=args.mail_to,
                      interval = args.interval,
                      mail_always = args.mail_always,
                      history = history,
                      options=args)
    watcher.run(args)


if __name__ == "__main__":
    main()
