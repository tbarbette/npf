" Vim syntax file
" Language: NPF syntax file
" Maintainer: Massimo Girondi
" Latest Revision: 10 June 2022

if exists("b:current_syntax")
  finish
endif


setlocal commentstring=//\ %s
syntax case match

setlocal iskeyword+=%
setlocal tabstop=2



syntax keyword node_kw path user addr tags nfs arch port

""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
" Sections will match in reverse order to handle overlapping names
syntax match pysections /\v(^\%|\:)\zs(pyexit)\ze( |$|\@)/
syntax match sections2 /\v(^\%|\:)\zs(|sendfile|late_variables)\ze( |$|\@)/ nextgroup=pysections
syntax match sections /\v(^\%|\:)\zs(info|config|script|exit|pypost|variables|import|require|file|init)\ze( |$|\@)/ nextgroup=sections2


""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
syntax match role /\v\@\zs[a-zA-Z0-9_]+\ze\s/
syntax match variables /\v\zs[a-zA-Z0-9_]+\ze\+?\??\=/
" After a tag, look for a section
syntax match tag /\v(^|,|\%)\zs([a-zA-Z0-9_,|!-]+)\ze(,|:)/ nextgroup=sections
syntax match comments /^\/\/.*/


" Match variables around
syntax match calledvariables /\v\zs\$\{?[a-zA-Z0-9_]+\}?\ze/


""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
syntax include @PYTHON syntax/python.vim
"syntax include @CLICK syntax/click.vim

" Match inline python code
syntax match inlineStart /\v\$\(\(/ contained
syntax match inlineStop /\v\)\)/ contained
syntax region inlinePy start="\v\$\(\(" end="\v\)\)" contains=@PYTHON,inlineStart,inlineStop,calledvariables transparent keepend

" Match Python regions
syntax region pyexitRegion start="\v.*pyexit.*" end= "\v\ze^\%" contains=@PYTHON,calledvariables,pysections,comments transparent keepend
" Try to highlight file with .py in the first line
syntax region PyScriptRegion start="\v.*(\%|\:)file.*\.py" end="\v\ze^\%" contains=@PYTHON,calledvariables,inlinePy,comments,role,sections,tag transparent keepend

""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
" Bash sections 
unlet b:current_syntax
syntax include @SH syntax/bash.vim

" We need to highlight the first line for each section, so we just include
" parts of it in the contains directive (not the best way thouh...)
syntax region initRegion start="\v.*(\%|\:)init.*" end="\v\ze^\%" contains=@SH,calledvariables,inlinePy,comments,role,tag,sections transparent keepend
syntax region scriptRegion start="\v.*(\%|\:)script.*" end="\v\ze^\%" contains=@SH,calledvariables,inlinePy,comments,sections,role,tag transparent keepend
syntax region exitRegion start="\v.*(\%|\:)exit.*" end="\v\ze^\%" contains=@SH,calledvariables,inlinePy,comments,role,sections,tag transparent keepend
" Try to highlight file with .sh in the first line
syntax region bashScriptRegion start="\v.*(\%|\:)file.*\.sh" end="\v\ze^\%" contains=@SH,calledvariables,inlinePy,comments,role,sections,tag transparent keepend

" Match click files (try to when there is a .click extension in the file like)
unlet b:current_syntax
syntax include @CLICK syntax/click.vim

syntax region bashScriptRegion start="\v.*(\%|\:)file.*\.click" end="\v\ze^\%" contains=@CLICK,calledvariables,inlinePy,comments,role,sections,tag transparent keepend

""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
" Handle config sections differently

syntax match configVar /\v\zs[a-zA-Z0-9_]+\ze\+?\??\=/ contained
syntax match configEntries /\v((\{|,))\zs[a-zA-Z0-9_]+\ze(\:|\,)/

syntax region configRegion start="\v.*(\%|\:)config.*" end="\v\ze^\%" transparent keepend contains=configEntries,tag,comments,configVar,role,sections,configVar,inlinePy



""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
highlight default link comments Comment
highlight default link role ToDo
highlight tags guifg=green
highlight role guifg=yellow
highlight sections guifg=pink cterm=bold
highlight sections2 guifg=pink cterm=bold
highlight pysections guifg=pink cterm=bold
highlight inlineStart guifg=yellow cterm=bold
highlight inlineStop guifg=yellow cterm=bold
highlight inline guifg=pink cterm=bold
highlight default link variables Structure
highlight tag guifg=aqua
highlight calledvariables guifg=green
highlight configRegion guifg=red cterm=bold
highlight default link configVar Structure
highlight default link configEntries Storage

" Tell vim that this is npf
let b:current_syntax = "npf"

