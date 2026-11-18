import re, sys
txt = open(sys.argv[1]).read()
# crude s-expr parser
def tokenize(s):
    return re.findall(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+', s)
def parse(toks):
    stack=[[]]
    for t in toks:
        if t=='(': stack.append([])
        elif t==')':
            x=stack.pop(); stack[-1].append(x)
        else: stack[-1].append(t.strip('"'))
    return stack[0]
tree=parse(tokenize(txt))[0]
def find(node,key):
    return [n for n in node if isinstance(n,list) and n and n[0]==key]
comps={}
for c in find(find(tree,'components')[0],'comp'):
    ref=find(c,'ref')[0][1]; val=find(c,'value')[0][1]
    fp=find(c,'footprint'); fp=fp[0][1] if fp else ''
    comps[ref]=(val,fp)
nets={}
for n in find(find(tree,'nets')[0],'net'):
    name=find(n,'name')[0][1]
    nodes=[(find(x,'ref')[0][1],find(x,'pin')[0][1],(find(x,'pinfunction') or [['','']])[0][1]) for x in find(n,'node')]
    nets[name]=nodes
mode=sys.argv[2] if len(sys.argv)>2 else 'nets'
if mode=='comps':
    for r in sorted(comps, key=lambda r:(re.sub(r'\d','',r),int(re.sub(r'\D','',r) or 0))):
        print(r, comps[r][0], comps[r][1])
elif mode=='nets':
    for name in sorted(nets):
        print(name, ' | '.join('%s.%s(%s)'%x for x in nets[name]))
elif mode=='part':
    for ref in sys.argv[3:]:
        print('==',ref,comps.get(ref))
        for name,nodes in sorted(nets.items()):
            for r,p,f in nodes:
                if r==ref: print('  pin %s %s -> %s  [%s]'%(p,f,name,', '.join('%s.%s'%(a,b) for a,b,c in nodes if a!=ref)))
