import multiprocessing
import queue
from pprint import pprint


def 进程处理(参数, 任务数, 图层, 图层锁):
    print(f'进程参数：{参数}')


def main(进程数=5, 输入=2):

    第一个任务队列 = multiprocessing.JoinableQueue()
    第二个任务队列 = multiprocessing.JoinableQueue()

    管理器 = multiprocessing.Manager()

    图层 = []
    for i in range(输入):
        图层.append(管理器.list())

    管理器 = None

    图层锁 = multiprocessing.Lock()
    任务数 = multiprocessing.Value('i', 0)

    进程列表 = []
    for i in range(2):
        参数 = i

        本地 = locals()
        本地.pop('i')
        本地.pop('任务数')
        本地.pop('参数')
        本地.pop('图层')
        本地.pop('图层锁')
        本地.pop('第一个任务队列')
        本地.pop('管理器')
        本地.pop('进程列表')
        本地.pop('第二个任务队列')

        本地['本地'] = None
        本地['进程'] = None

        pprint(本地)

        进程 = multiprocessing.Process(target=进程处理, args=(参数, 第二个任务队列, 管理器, 本地))
        进程.name = f'进程{"{:0>2d}".format(i)}'
        进程.start()
        进程列表.append(进程)


if __name__ == '__main__':
    main()