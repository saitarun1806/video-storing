package com.example.drm.mpd;

import com.example.drm.discord.DiscordUploader.UploadResult;import com.example.drm.util.Log;import org.w3c.dom.*;import javax.xml.parsers.*;import javax.xml.transform.*;import javax.xml.transform.dom.DOMSource;import javax.xml.transform.stream.StreamResult;import java.nio.file.*;import java.util.*;

public class MpdRewriter {
 private static final String MPD_NS="urn:mpeg:dash:schema:mpd:2011";private static final String CENC_NS="urn:mpeg:cenc:2013";private static final String CP="ContentProtection";
 public void rewrite(Path mpd,Map<String,UploadResult> uploaded,String kid)throws Exception{
  DocumentBuilderFactory f=DocumentBuilderFactory.newInstance();f.setNamespaceAware(true);Document d=f.newDocumentBuilder().parse(mpd.toFile());Element root=d.getDocumentElement();root.setAttribute("xmlns:cenc",CENC_NS);
  NodeList sets=root.getElementsByTagNameNS(MPD_NS,"AdaptationSet");for(int i=0;i<sets.getLength();i++)addProtection(d,(Element)sets.item(i),kid);
  NodeList templates=root.getElementsByTagNameNS(MPD_NS,"SegmentTemplate");List<Element> copy=new ArrayList<>();for(int i=0;i<templates.getLength();i++)copy.add((Element)templates.item(i));
  for(Element t:copy){Element rep=parentRepresentation(t);if(rep==null)continue;String rid=rep.getAttribute("id");String init=t.getAttribute("initialization");if(rid.isBlank()||init.isBlank())continue;String initName=init.replace("$RepresentationID$",rid);UploadResult iu=uploaded.get(Path.of(initName).getFileName().toString());if(iu==null)throw new IllegalStateException("Initialization not uploaded: "+initName);
   Element sl=d.createElementNS(MPD_NS,"SegmentList");NamedNodeMap attrs=t.getAttributes();for(int a=0;a<attrs.getLength();a++){Node n=attrs.item(a);if(!n.getNodeName().equals("initialization")&&!n.getNodeName().equals("media"))sl.setAttribute(n.getNodeName(),n.getNodeValue());}
   Element ini=d.createElementNS(MPD_NS,"Initialization");ini.setAttribute("sourceURL",iu.resolverUrl());sl.appendChild(ini);Node timeline=firstChild(t,"SegmentTimeline");if(timeline!=null)sl.appendChild(timeline.cloneNode(true));
   String prefix="chunk-"+rid+"-";try(var s=Files.list(mpd.getParent())){s.filter(p->Files.isRegularFile(p)&&p.getFileName().toString().startsWith(prefix)&&p.getFileName().toString().endsWith(".m4s")).sorted().forEach(p->{UploadResult u=uploaded.get(p.getFileName().toString());if(u==null)throw new RuntimeException("Segment not uploaded: "+p.getFileName());Element su=d.createElementNS(MPD_NS,"SegmentURL");su.setAttribute("media",u.resolverUrl());sl.appendChild(su);});}
   Node parent=t.getParentNode();parent.replaceChild(sl,t);
  }
  Transformer tr=TransformerFactory.newInstance().newTransformer();tr.setOutputProperty(OutputKeys.INDENT,"yes");tr.setOutputProperty(OutputKeys.ENCODING,"UTF-8");tr.transform(new DOMSource(d),new StreamResult(mpd.toFile()));Log.ok("MPD rewritten with CDN resolver URLs");
 }
 private Element parentRepresentation(Element t){Node n=t.getParentNode();while(n!=null){if(n instanceof Element e&&e.getLocalName().equals("Representation"))return e;n=n.getParentNode();}return null;}
 private Node firstChild(Element e,String local){NodeList n=e.getElementsByTagNameNS(MPD_NS,local);return n.getLength()==0?null:n.item(0);}
 private void addProtection(Document d,Element set,String kid){for(Node n=newChildList(set);n!=null;){Node next=n.getNextSibling();if(n instanceof Element e&&e.getLocalName().equals(CP))set.removeChild(n);n=next;}
  String k=formatKid(kid);Element c=d.createElementNS(MPD_NS,CP);c.setAttribute("schemeIdUri","urn:mpeg:dash:mp4protection:2011");c.setAttribute("value","cenc");c.setAttributeNS(CENC_NS,"cenc:default_KID",k);set.insertBefore(c,set.getFirstChild());Element ck=d.createElementNS(MPD_NS,CP);ck.setAttribute("schemeIdUri","urn:uuid:e2719d58-a985-b3c9-781a-b030af78d30e");ck.setAttribute("value","ClearKey1.0");set.insertBefore(ck,c.getNextSibling());}
 private Node newChildList(Element e){return e.getFirstChild();}
 private String formatKid(String x){x=x.replace("-","").toLowerCase(Locale.ROOT);if(!x.matches("[0-9a-f]{32}"))throw new IllegalArgumentException("Invalid KID");return x.substring(0,8)+"-"+x.substring(8,12)+"-"+x.substring(12,16)+"-"+x.substring(16,20)+"-"+x.substring(20);}
}
