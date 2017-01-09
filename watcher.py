#!/usr/bin/python3
import argparse
import time
from email.mime.text import MIMEText
from typing import Tuple, List

from src.regression import *

import smtplib

from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart


def mail(mail_from, mail_to, subject, body, images=[], bodytype='text'):
    print(subject)
    COMMASPACE = ', '

    # Create the container (outer) email message.
    msg = MIMEMultipart()
    msg['Subject'] = subject

    if mail_from:
        msg['From'] = mail_from
    msg['To'] = COMMASPACE.join(mail_to)
    msg.attach(MIMEText(body, bodytype))

    for img, cid in images:
        img = MIMEImage(img)
        img.add_header('Content-ID', '<' + cid + '>')
        msg.attach(img)

    s = smtplib.SMTP('localhost')
    s.send_message(msg)
    s.quit()


def check_all_repos(repo_list: List[Tuple[Repository, List[Testie]]], mail_to: List[str], mail_from: str, history: int,
                    quiet: bool = False, graph_num: int = 8, mail_always=True):
    for repo, testies in repo_list:
        gitrepo = repo.gitrepo()
        commit = next(gitrepo.iter_commits('origin/' + repo.branch))
        uuid = commit.hexsha[:7]
        if repo.last_build and uuid == repo.last_build.uuid:
            if not quiet:
                print("[%s] No new uuid !" % (repo.name))
            continue

        if (history > 0 and repo.last_build):
            build = repo.last_build_before(repo.last_build)
        else:
            build = Build(repo, uuid)
        print("[%s] New uuid %s !" % (repo.name, build.uuid))

        graphs = []

        if not build.build_if_needed():
            mail(subject="[%s] Could not compile %s !" % (repo.name, uuid), mail_to=mail_to, body='',
                 mail_from=mail_from)
            # Pass if not last
            if (build.uuid != uuid):
                repo.last_build = build
            continue
        nok = 0
        body = '<html>'
        body += 'Detailed results for %s :<br />' % build.uuid
        for testie in testies:
            print("[%s] Running testie %s..." % (repo.name, testie.filename))
            regression = Regression(testie)
            if repo.last_build:
                try:
                    old_all_results = repo.last_build.readUuid(testie)
                except FileNotFoundError:
                    old_all_results = None
            else:
                old_all_results = None
            all_results = testie.execute_all(build)
            tests_failed, tests_total = regression.compare(testie.variables, all_results, build, old_all_results,
                                                           repo.last_build)
            body += '<b>%s</b> :' % build.uuid
            if tests_failed == 0:
                nok += 1
                body += '<span style="color:green;">PASSED</span><br />'
            else:
                print("[%s] Testie %s FAILED !" % (repo.name, testie.filename))
                body += '<span style="color:red;">FAILED</span> with %d/%d points out of constraints.<br />' % (
                    tests_failed, tests_total)
            build.writeUuid(testie, all_results)

            grapher = Grapher()
            graphs_series = [(testie, build, all_results)]

            last_graph = build  # last graph is the oldest build in the series
            if repo.last_build and old_all_results:
                graphs_series.append((testie, repo.last_build, old_all_results))
                last_graph = repo.last_build

            graphs_series += repo.get_old_results(last_graph, graph_num - len(graphs_series), testie)
            g = grapher.graph(series=graphs_series, title=testie.get_title(),
                              filename=None, graph_variables=testie.variables)
            graphs.append((g, testie.filename))
            body += '<img src="cid:%s"><br/><br/>' % testie.filename

        build.writeResults()
        repo.last_build = build
        body += '</html>'
        if nok < len(testies) or mail_always:
            mail(subject="[%s] Finished run for %s, %d/%d tests passed" % (repo.name, build.uuid, nok, len(testies)),
             body=body,
             bodytype='html',
             mail_from=mail_from,
             mail_to=mail_to, images=graphs)


def main():
    parser = argparse.ArgumentParser(description='Click Watcher')
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

        testies = Testie.expandFolder(args.testie, tags=tags, quiet=args.quiet)
        repo_list.append((repo, testies))

    terminate = False
    while not terminate:
        check_all_repos(repo_list, history=history, quiet=args.quiet, graph_num=args.graph_num,
                        mail_to=args.mail_to, mail_from=args.mail_from,mail_always = args.mail_always)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
