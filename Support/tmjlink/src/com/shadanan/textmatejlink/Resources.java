package com.shadanan.textmatejlink;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.UUID;

import com.wolfram.jlink.Expr;
import com.wolfram.jlink.ExprFormatException;
import com.wolfram.jlink.KernelLink;
import com.wolfram.jlink.MathLink;
import com.wolfram.jlink.MathLinkException;
import com.wolfram.jlink.MathLinkFactory;
import com.wolfram.jlink.PacketArrivedEvent;
import com.wolfram.jlink.PacketListener;

public class Resources implements PacketListener {
	public static final Expr NULLEXPR = new Expr(Expr.SYMBOL, "Null");
	
	private String sessionId = null;
	private String cacheFolder = null;
	private KernelLink kernelLink = null;
	private int currentCount = 0;
	private String[] mlargs = null;
	private ArrayList<Resources.Resource> resources = null;
	private Session session;
	
	public Resources(String sessionId, String cacheFolder, String[] mlargs) 
			throws MathLinkException, IOException {
		this.sessionId = sessionId;
		this.cacheFolder = cacheFolder;
		this.mlargs = mlargs;
		this.resources = new ArrayList<Resources.Resource>();
		
		// Allocate the kernel link and register packet listener
		kernelLink = MathLinkFactory.createKernelLink(mlargs);
		kernelLink.addPacketListener(this);
		kernelLink.discardAnswer();
		
		// Create cache folder
		File sessionFolderPointer = getSessionFolder();
		if (sessionFolderPointer.exists())
			delete(sessionFolderPointer);
		sessionFolderPointer.mkdir();
	}
	
	public static boolean delete(File file) {
		if (file.isDirectory()) {
			for (File child : file.listFiles()) {
				boolean success = delete(child);
				if (!success) return false;
			}
		}
		
		return file.delete();
	}
	
	public String getSessionId() {
		return sessionId;
	}
	
	public int getSize() {
		return resources.size();
	}
	
	public File getSessionFolder() {
		return new File(cacheFolder + "/" + sessionId);
	}
	
	public File getNamedFile(String filename) {
		File file = new File(cacheFolder + "/" + sessionId + "/" + filename);
		return file;
	}
	
	public void reconnect() throws MathLinkException {
		kernelLink.removePacketListener(this);
		kernelLink.close();
		
		kernelLink = MathLinkFactory.createKernelLink(mlargs);
		kernelLink.addPacketListener(this);
		kernelLink.discardAnswer();
	}
	
	public void close() {
		// Close the kernel link
		kernelLink.close();
		
		// Release all allocated resources
		release();
		
		// Delete the cache folder (it should be empty now)
		File cacheFp = getSessionFolder();
		if (cacheFp.exists()) cacheFp.delete();
	}
	
	public void release() {
		// Delete resources allocated
		Iterator<Resource> iterator = resources.iterator();
		while (iterator.hasNext()) {
			Resource resource = iterator.next();
			resource.release();
			iterator.remove();
		}
	}
	
	public String getSuggestions() throws MathLinkException, ExprFormatException {
		StringBuilder result = new StringBuilder();
		result.append("[");
		
		kernelLink.evaluate("$ContextPath");
		kernelLink.waitForAnswer();
		Expr contexts = kernelLink.getExpr();
		
		for (int j = 1; j <= contexts.length(); j++) {
			String context = contexts.part(j).asString();
			kernelLink.evaluate("Names[\"" + context + "*\"]");
			kernelLink.waitForAnswer();
			Expr symbols = kernelLink.getExpr();
			
			for (int i = 1; i <= symbols.length(); i++) {
				result.append('"');
				result.append(symbols.part(i).asString());
				result.append('"');
				result.append(",");
			}
		}
		
		result.append("]");
		return result.toString();
	}
	
	private String commify(long number) {
		StringBuilder result = new StringBuilder();
		String num = String.valueOf(number);
		
		int pos = num.length();
		while (pos > 0) {
			int start = pos - 3;
			result.insert(0, num.substring(Math.max(start, 0), pos));
			if (start > 0)
				result.insert(0, ",");
			pos = start;
		}
		
		return result.toString();
	}
	
	public String evaluate(String query) throws MathLinkException, IOException {
		kernelLink.evaluate(query);
		kernelLink.waitForAnswer();
		Expr result = kernelLink.getExpr();
		kernelLink.newPacket();
		if (!result.equals(NULLEXPR))
			return result.toString();
		return null;
	}
	
	public void evaluate(String query, boolean evalToImage, Session session) 
			throws MathLinkException, IOException {
		long mark = System.currentTimeMillis();
		this.session = session;
		
		session.sendInline("<div id='resource_" + currentCount + "' class='cellgroup'>");
		
		// Log the input
		Resource input = new Resource(query); 
		resources.add(input);
		session.sendInline(input.render(true));
		
		kernelLink.evaluate(query);
		kernelLink.waitForAnswer();
		Expr result = kernelLink.getExpr();
		
		if (!result.equals(NULLEXPR)) {
			// Log the output as fullform text
			Resource textResource = new Resource(MathLink.RETURNPKT, result);
			byte[] data = null;
			
			if (evalToImage || textResource.isGraphics())
				data = kernelLink.evaluateToImage(result, 0, 0);
			
			if (data != null) {
				Resource graphicsResource = new Resource(MathLink.DISPLAYPKT, data);
				resources.add(graphicsResource);
				session.sendInline(graphicsResource.render(true));
				textResource.subdue();
				session.sendInline(textResource.render(false));
			} else {
				session.sendInline(textResource.render(true));
			}
			
			resources.add(textResource);
		}
		
		// Done with this. Move on...
		kernelLink.newPacket();
		currentCount++;
		
		input.setTime(System.currentTimeMillis() - mark);
		session.sendInline("<div class='time'>" + commify(input.getTime()) + "ms</div></div>");
	}
	
	public String render() {
		boolean renderedDisplay = false;
		int currentCount = -1;
		long executeTime = -1;
		StringBuilder content = new StringBuilder();
		
		for (Resource resource : resources) {
			if (currentCount == -1) {
				executeTime = -1;
				currentCount = resource.getCount();
				content.append("<div id='resource_" + currentCount + "' class='cellgroup'>");
			}
			
			if (resource.getTime() != -1)
				executeTime = resource.getTime();

			if (resource.getCount() != currentCount) {
				if (executeTime != -1)
					content.append("<div class='time'>" + commify(executeTime) + "ms</div>");
				
				content.append("</div>");
				currentCount = resource.getCount();
				content.append("<div id='resource_" + currentCount + "' class='cellgroup'>");
				renderedDisplay = false;
			}
			
			if (resource.type == MathLink.DISPLAYPKT) {
				renderedDisplay = true;
				content.append(resource.render(true));
			} else if (resource.type == MathLink.RETURNPKT) {
				if (!renderedDisplay)
					content.append(resource.render(true));
			} else {
				content.append(resource.render(true));
			}
		}
		
		if (currentCount != -1) {
			if (executeTime != -1)
				content.append("<div class='time'>" + commify(executeTime) + "ms</div>");
			content.append("</div>");
		}
		
		return content.toString();
	}
	
	class Resource {
		private int type;
		private String value;
		private int count;
		private boolean subdue;
		private Expr expr;
		private long time;
		
		public Resource(String value) {
			this.type = -1;
			this.value = value;
			this.count = currentCount;
			this.subdue = false;
			this.expr = null;
			this.time = -1;
		}
		
		public Resource(int type, Expr expr) {
			this.type = type;
			this.value = null;
			this.count = currentCount;
			this.subdue = false;
			this.expr = expr;
			this.time = -1;
		}
		
		public Resource(int type, String value) {
			this.type = type;
			this.value = value;
			this.count = currentCount;
			this.subdue = false;
			this.expr = null;
			this.time = -1;
		}
		
		public Resource(int type, byte[] data) throws IOException {
			this.type = type;
			this.value = UUID.randomUUID().toString() + ".gif";
			this.count = currentCount;
			this.subdue = false;
			this.expr = null;
			this.time = -1;
			
			FileOutputStream fp = new FileOutputStream(getFilePointer());
			fp.write(data);
			fp.close();
		}
		
		public void setTime(long time) {
			this.time = time;
		}
		
		public long getTime() {
			return time;
		}
		
		public void subdue() {
			subdue = true;
		}
		
		public int getType() {
			return type;
		}
		
		public String getValue() {
			return value == null ? expr.toString() : value;
		}
		
		public String getHtmlEscapedValue() {
		  return getHtmlEscapedValue(false);
		}
		
		public String getHtmlEscapedValue(boolean autoTrim) {
			StringBuilder sb = new StringBuilder();
			String base = value == null ? expr.toString() : value;
			
			if (autoTrim) {
	      base = base.replaceAll("\\\\\\n\\s\\n>\\s\\s", "");
			}
			
			for (int i = 0; i < base.length(); i++) {
				char c = base.charAt(i);
				switch (c) {
					case '<': sb.append("&lt;"); break;
					case '>': sb.append("&gt;"); break;
					case '&': sb.append("&amp;"); break;
					case '"': sb.append("&quot;"); break;
					case '�': sb.append("&agrave;"); break;
					case '�': sb.append("&Agrave;"); break;
					case '�': sb.append("&acirc;"); break;
					case '�': sb.append("&Acirc;"); break;
					case '�': sb.append("&auml;"); break;
					case '�': sb.append("&Auml;"); break;
					case '�': sb.append("&aring;"); break;
					case '�': sb.append("&Aring;"); break;
					case '�': sb.append("&aelig;"); break;
					case '�': sb.append("&AElig;"); break;
					case '�': sb.append("&ccedil;"); break;
					case '�': sb.append("&Ccedil;"); break;
					case '�': sb.append("&eacute;"); break;
					case '�': sb.append("&Eacute;"); break;
					case '�': sb.append("&egrave;"); break;
					case '�': sb.append("&Egrave;"); break;
					case '�': sb.append("&ecirc;"); break;
					case '�': sb.append("&Ecirc;"); break;
					case '�': sb.append("&euml;"); break;
					case '�': sb.append("&Euml;"); break;
					case '�': sb.append("&iuml;"); break;
					case '�': sb.append("&Iuml;"); break;
					case '�': sb.append("&ocirc;"); break;
					case '�': sb.append("&Ocirc;"); break;
					case '�': sb.append("&ouml;"); break;
					case '�': sb.append("&Ouml;"); break;
					case '�': sb.append("&oslash;"); break;
					case '�': sb.append("&Oslash;"); break;
					case '�': sb.append("&szlig;"); break;
					case '�': sb.append("&ugrave;"); break;
					case '�': sb.append("&Ugrave;"); break;         
					case '�': sb.append("&ucirc;"); break;         
					case '�': sb.append("&Ucirc;"); break;
					case '�': sb.append("&uuml;"); break;
					case '�': sb.append("&Uuml;"); break;
					case '�': sb.append("&reg;"); break;         
					case '�': sb.append("&copy;"); break;   
					case '�': sb.append("&euro;"); break;
					// be carefull with this one (non-breaking whitee space)
					// case ' ': sb.append("&nbsp;"); break;
					// case '\n': sb.append("<br />"); break;
					default:  sb.append(c); break;
				}
			}
			
			return sb.toString();
		}
		
		public int getCount() {
			return count;
		}
		
		public File getFilePointer() {
			return getNamedFile(value);
		}
		
		public boolean isGraphics() {
			if (type != MathLink.RETURNPKT) {
				throw new RuntimeException("This method can only be called on RETURNPKT resource.");
			}
			
			Expr head = expr.head();
			if (head.toString().equals("List")) {
				if (expr.length() == 0)
					return false;
				else
					head = expr.part(1).head();
			}

			if (head.toString().equals("InputForm"))
				return false;
			
			if (head.toString().equals("Graphics"))
				return true;
			
			if (head.toString().equals("GraphicsRow"))
				return true;
			
			if (head.toString().equals("Graphics3D"))
				return true;
			
			if (head.toString().equals("Labeled"))
				return true;
			
			if (head.toString().equals("Grid"))
			  return true;
			
			if (head.toString().equals("Row"))
			  return true;
			
			if (head.toString().equals("Column"))
			  return true;
			
			if (head.toString().endsWith("Form"))
				return true;
			
			return false;
		}
		
		public void release() {
			if (type == MathLink.DISPLAYPKT) {
				File file = getFilePointer();
				if (file.exists()) file.delete();
			}
		}
		
		public String render(boolean visible) {
			StringBuilder result = new StringBuilder();
			
			String style = "";
			if (!visible)
				style = " style='display:none;'";
			
			if (type == -1) {
				result.append("<div class='cell input'" + style + ">");
				result.append("  <div class='margin'>In[" + count + "] := </div>");
				result.append("  <div class='content'>" + getHtmlEscapedValue() + "</div>");
				result.append("</div>");
			}
			
			if (type == MathLink.TEXTPKT) {
				result.append("<div class='cell text'" + style + ">");
				result.append("  <div class='margin'>Msg[" + count + "] := </div>");
				result.append("  <div class='content'>" + getHtmlEscapedValue(true) + "</div>");
				result.append("</div>");
			}
			
			if (type == MathLink.MESSAGEPKT) {
				result.append("<div class='cell message'" + style + ">");
				result.append("  <div class='margin'>Msg[" + count + "] := </div>");
				result.append("  <div class='content'>" + getHtmlEscapedValue(true) + "</div>");
				result.append("</div>");
			}
			
			if (type == MathLink.DISPLAYPKT) {
				result.append("<div class='cell display'" + style + ">");
				result.append("  <div class='margin'>Out[" + count + "] := </div>");
				result.append("  <div class='content'>");
				result.append("    <img src='file://" + getFilePointer() + "' onclick='toggle(" + count + ")' />");
				result.append("  </div>");
				result.append("</div>");
			}
			
			if (type == MathLink.RETURNPKT) {
				String cls = "";
				if (subdue)
					cls = " subdue";
				
				result.append("<div class='cell return" + cls + "'" + style + ">");
				result.append("  <div class='margin'>Out[" + count + "] := </div>");
				result.append("  <div class='content'>" + getHtmlEscapedValue() + "</div>");
				result.append("</div>");
			}
			
			return result.toString();
		}
	}

	@Override
  public boolean packetArrived(PacketArrivedEvent evt) throws MathLinkException {
		KernelLink ml = (KernelLink)evt.getSource();
		
		if (evt.getPktType() == MathLink.TEXTPKT) {
			Resource resource = new Resource(evt.getPktType(), ml.getString()); 
			resources.add(resource);
			session.sendInline(resource.render(true));
		}
		
		if (evt.getPktType() == MathLink.MESSAGEPKT) {
			Resource resource = new Resource(evt.getPktType(), ml.getString());
			resources.add(resource);
			session.sendInline(resource.render(true));
		}
		
		for (Field field : MathLink.class.getFields()) {
			if (field.getName().endsWith("PKT")) {
				try {
					if (evt.getPktType() == field.getInt(field)) {
						System.out.println("Received Mathematica Packet: " + field.getName() + " (" + evt.getPktType() + ")");
					}
				} catch (IllegalArgumentException e) {
					System.out.println(e.getMessage());
				} catch (IllegalAccessException e) {
					System.out.println(e.getMessage());
				}
			}
		}
		
		return true;
	}
	
	public static void main(String args[]) {
	  String data = "\"user_count_tablestats\" -> {\"chart\" -> \"user_count_tablestats.gif\", \"colors\"\\\n" +
	                " \n" + 
	                ">   -> {\"e63221\", \"5b0e04\", \"b04e00\", \"fac742\", \"a1a13f\", \"527b28\", \"4e977d\",\\\n" +
                  " \n" + 
                  ">   \"316f74\", \"549bbe\", \"104283\"}, \"labels\" -> {\"user base size\", \"verified\\\n" +
                  " \n" + 
                  ">   email\", \"trial users\"}}";
	  data = data.replaceAll("\\\\\\n\\s\\n>\\s\\s", "");
	  System.out.println(data);
	}
}
