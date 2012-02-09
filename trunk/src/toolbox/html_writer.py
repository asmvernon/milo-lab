#!/usr/bin/python

"""
html_writer.py - Construct HTML pages

"""

import datetime
import os
import types
import xml.dom.minidom
from toolbox.util import _mkdir, get_current_svn_revision

class BaseHtmlWriter:
    def __init__(self):
        self.div_counter = 0
        pass

    def relative_to_full_path(self, relpath):
        raise Exception("class not implemented")

    def write(self):
        raise Exception("class not implemented")

    def write_header(self):
        self.write('<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">\n')
        self.write('<head>\n')
        self.write('<script type="text/javascript" src="expandCollapse.js"></script>\n')
        self.write('</head>\n')
        self.write('<html>\n<body>\n')
        
        now = datetime.datetime.now()
        self.write('<div>Written at %s</div>' % now)
        
        r = get_current_svn_revision()
        if r:
            self.write('<a href=https://code.google.com/p/milo-lab/source/browse/trunk/?r=%d>milo-lab SVN r%d</a></br>' % (r,r))

    def write_js(self, path):
        if (os.path.exists(path + '/expandCollapse.js')):
            return
        file = open(path + '/expandCollapse.js', 'w')
        file.write("""function toggleMe(a){
  var e=document.getElementById(a);
  if(!e)return true;
  if(e.style.display=="none"){
    e.style.display="block"
  } else {
    e.style.display="none"
  }
  return true;
}
""")
        file.close()
        
    def write_ol(self, l):
        self.write("<ol>\n")
        for mem in l:
            self.write("  <li>%s</li>\n" % str(mem))
        self.write("</ol>\n")
            
    def write_ul(self, l):
        self.write("<ul>\n")
        for mem in l:
            self.write("  <li>%s</li>\n" % str(mem))
        self.write("</ul>\n")
        
    def write_table(self, dict_list, headers=None, border=1):
        """
            In order to print the row number, use the title '#' in headers and
            write_table() will automatically fill that column with the row numbers.
        """
        def to_string(x):
            if type(x) == types.StringType:
                return x
            else:
                return str(x)
        
        if not headers:
            headers = set()
            for dict in dict_list:
                for key in dict.keys():
                    headers.add(to_string(key))
            headers = sorted(headers)
        
        self.write('<table border=%d>\n' % border)
        self.write('<tr><td><b>' + '</b></td><td><b>'.join(headers) + '</b></td></tr>\n')
        for i, d in enumerate(dict_list):
            d['#'] = '%d' % i
            values = [to_string(d.get(key, "")) for key in headers]
            self.write('<tr><td>' + '</td><td>'.join(values) + '</td></tr>\n')
        self.write("</table>\n")
        
    def table_start(self, border=1):
        self.write('<table border=%d>\n' % border)

    def table_writerow(self, values):
        self.write('<tr><td>' + '</td><td>'.join(values) + '</td></tr>\n')
    
    def table_end(self):
        self.write("</table>\n")
        
    def insert_toggle(self, div_id=None, start_here=False, label='Show'):
        if not div_id:
            div_id = "DIV%05d" % self.div_counter
            self.div_counter += 1
        elif type(div_id) != types.StringType:
            raise ValueError("HTML div ID must be a string")
        self.write('<input type="button" class="button" onclick="return toggleMe(\'%s\')" value="%s">\n'
                   % (div_id, label))
        if start_here:
            self.div_start(div_id)
        return div_id
    
    def div_start(self, div_id):
        self.write('<div id="%s" style="display:none">' % div_id)
        
    def div_end(self):
        self.write('</div>\n')
    
    def embed_img(self, fig_fname, alternative_string=""):
        self.write('<img src="' + fig_fname + '" atl="' + alternative_string + '" />')
    
    def embed_svg(self, fig_fname, width=320, height=240, name=''):
        self.write('<a href="%s.svg">' % name)
        self.extract_svg_from_file(fig_fname, width=width, height=height)
        self.write('</a>')

        #self.write('<object data="%s" type="image/svg+xml" width="%dpt" height="%dpt" name="%s" frameborder="0" marginwidth="0" marginheight="0"/></object>'
        #           % (fig_fname, width, height, name))
    
    def embed_matplotlib_figure(self, fig, width=None, height=None, name=None):
        """
            Adds a matplotlib figure into the HTML as an inline SVG
            
            Arguments:
                fig          - a matplotlib Figure object
                width        - the desired width of the figure in pixels
                height       - the desired height of the figure in pixels
                name         - if not None, the SVG will be written to a file with that name will
                               be linked to from the inline figure
        """
        if name:
            svg_filename = self.relative_to_full_path(name + '.svg')
            self.write('<a href="%s.svg">' % name)
        else:
            svg_filename = '.svg'
        
        width = width or (fig.get_figwidth() * fig.get_dpi())
        height = height or (fig.get_figheight() * fig.get_dpi())
        
        fig.savefig(svg_filename, format='svg')
        self.extract_svg_from_file(svg_filename, width=width, height=height)
        
        if name:
            self.write('</a>')
        else:
            os.remove(svg_filename)

    def embed_dot_inline(self, Gdot, width=320, height=240, name=None):
        """
            Converts the DOT graph to an SVG DOM and uses the inline SVG option to 
            add it directly into the HTML (without creating a separate SVG file).
        """
        if name:
            svg_filename = self.relative_to_full_path(name + '.svg')
            self.write('<a href="%s.svg">' % name)
        else:
            svg_filename = '.svg'

        Gdot.write(svg_filename, prog='dot', format='svg')
        self.extract_svg_from_file(svg_filename, width=width, height=height)
        if name:
            self.write('</a>')
        else:
            os.remove(svg_filename)

    def embed_dot(self, Gdot, name, width=320, height=240):
        """
            Converts the DOT graph to an SVG DOM and uses the inline SVG option to 
            add it directly into the HTML (without creating a separate SVG file).
        """
        svg_filename = self.relative_to_full_path(name + '.svg')
        Gdot.write(svg_filename, prog='dot', format='svg')
        self.embed_svg(svg_filename, width=width, height=height, name=name)

    def extract_svg_from_xmldom(self, dom, width=320, height=240):
        svg = dom.getElementsByTagName("svg")[0]
        svg.setAttribute('width', '%dpt' % width)
        svg.setAttribute('height', '%dpt' % height)
        self.write(svg.toprettyxml(indent='  ', newl=''))
                
    def extract_svg_from_file(self, fname, width=320, height=240):
        xmldom = xml.dom.minidom.parse(fname)
        self.extract_svg_from_xmldom(xmldom, width, height)
    
    def branch(self, relative_path, link_text=None):
        """
            Branches the HTML file by creating a new HTML and adding a link to it with the desired text
        """
        if (link_text == None):
            link_text = relative_path
            
        self.write("<a href=\"" + relative_path + ".html\">" + link_text + "</a>")
        return HtmlWriter(os.path.join(self.filepath, relative_path + ".html"))
    
    def close(self):
        self.write("</body>\n</html>\n")

class NullHtmlWriter(BaseHtmlWriter):
    def __init__(self):
        BaseHtmlWriter.__init__(self)
        self.filename = None
    
    def write(self, str):
        pass
    
    def relative_to_full_path(self, relpath):
        pass


class HtmlWriter(BaseHtmlWriter):
    def __init__(self, filename, force_path_creation=True, flush_always=True):
        BaseHtmlWriter.__init__(self)
        self.filename = filename
        self.filepath = os.path.dirname(filename)
        self.flush_always = flush_always
        if (not os.path.exists(self.filepath)):
            if (force_path_creation and not os.path.exists(self.filepath)):
                _mkdir(self.filepath)
            else:
                raise Exception("cannot write to HTML file %s since the directory doesn't exist" % filename)
        
        self.file = open(self.filename, "w")
        self.write_header()
        self.write_js(self.filepath)
    
    def relative_to_full_path(self, relpath):
        return self.filepath + "/" + relpath

    def write(self, str):
        if (self.file == None):
            raise Exception("cannot write to this HTML since it is already closed")
        self.file.write(str)
        if (self.flush_always):
            self.file.flush()
    
    def __del__(self):
        if self.file:
            self.close()
        
    def close(self):
        BaseHtmlWriter.close(self)
        self.file.flush()
        self.file.close()
        self.file = None

def test():
    html_write = HtmlWriter("../res/test.html")
    html_write.write("<h1>hello world</h1>\n")
    import pylab
    fig = pylab.figure()
    pylab.plot([1, 2, 3, 4], [4, 3, 2, 1], 'g--')
    html_write.embed_matplotlib_figure(fig, 320, 240, name='test')

if __name__ == '__main__':
    test()
